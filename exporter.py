"""Writes an imported Blur model back with the edits made in Blender.

The model's own file is the starting point (its path is on the root empty,
"blur_model"): every mesh made by the importer names the part behind each of
its material slots ("blur_parts"), so the faces of a slot become that part's
new geometry. What Blender holds is what gets written: a part whose mesh was
deleted, or whose slot has no faces left, stops being drawn (the importer
records what it made, "blur_imported", so deleted is told apart from never
imported: parts that weren't imported keep their old geometry). A mesh moved
under another element's empty moves its parts to that element.

Per vertex the exporter writes position, normal, both UV sets and colour,
in the part's own vertex format. Anything else a vertex carries (damage
offsets on cars, bone slots and weights on characters) comes from the vertex
it was imported from (the "blur_vertex" attribute) while it stays in place,
else from the nearest vertex the part had before. Vertices left in place also
keep their exact normal while the mesh still has the imported (custom)
normals; after Clear Custom Split Normals, Blender's own normals are written.

Detail levels: a part's level n comes from the "LOD<n>" mesh if it was
imported, else from the next more detailed level that is there (so editing
only the LOD0 mesh draws the edit at every distance). Levels the part didn't
use stay unused. Parts that draw exactly as before keep their bytes.

Placement: meshes are measured against where the file places their element
("blur_matrix" on the element empties), so moving, turning or scaling a part
or its empty moves the part's vertices.

Materials: for each part, the material in its slot (most detailed level) must
use the part's own effect (another effect makes it a new part); its number
inputs and texture slots are written into the part's material values. Parts
that shared material values but have different materials now get their own. A texture slot can take any image the model
holds, or a new picture: a .dds is stored as it is, other pictures are
compressed to DXT1/DXT5 with mipmaps, and added to the model's texture table.

Collision: convex hulls edited, moved or deleted in Blender and moved bodies
are written into the Coll chunk ("blur_shape" on each collision object says
which shape it is); other collision edits are listed as not written.
"""

import copy
import re
import struct

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, kdtree

from . import importer, materials
from .blur import chunks, collision, dds, parts, scene, textures
from .blur import model as blurmodel


class ExportError(Exception):
    pass


def model_root(obj):
    """The importer's root empty above `obj` (or `obj` itself), or None."""
    while obj is not None:
        if "blur_model" in obj:
            return obj
        obj = obj.parent
    return None


def _model_objects(root):
    """The model's objects: everything under the root empty, and objects of the model's
    collections that came from it (a mesh whose element empty was deleted stays in)."""
    out = list(root.children_recursive)
    seen = set(out)
    for coll in root.users_collection:
        for obj in coll.all_objects:
            if obj not in seen and obj is not root and ("blur_parts" in obj or "blur_shape" in obj):
                out.append(obj)
                seen.add(obj)
    return out


def _parent_element(obj, root):
    """The element of the nearest element empty above `obj`, or None (under the root itself,
    or outside the model)."""
    o = obj.parent
    while o is not None and o is not root:
        if o.type == "EMPTY" and "blur_element" in o and "blur_collision" not in o:
            return int(o["blur_element"])
        o = o.parent
    return None


def _world(obj):
    """The object's placement from its parent chain. (matrix_world isn't kept up to date for
    objects in excluded collections, such as the hidden detail levels.)"""
    m = obj.matrix_parent_inverse @ obj.matrix_basis
    return _world(obj.parent) @ m if obj.parent is not None else m


def element_of(obj, root):
    """The Blur element an object belongs to: its own "blur_element", else the nearest parent
    element empty's, else 0 (DefaultElement)."""
    if "blur_element" in obj and obj["blur_element"] >= 0:
        return int(obj["blur_element"])
    o = obj.parent
    while o is not None and o is not root:
        if o.type == "EMPTY" and "blur_element" in o:
            return int(o["blur_element"])
        o = o.parent
    return 0


def _matrix(values):
    m = list(values)
    return Matrix([m[i:i + 4] for i in range(0, 16, 4)])


def _element_space(obj, root, empties, element=None, placed=None):
    """Matrix from the object's local space into its Blur element's space, as the file places
    that element: moving or turning an element's empty in Blender moves its part. `placed`:
    element -> the file's placement, for elements whose empty was deleted."""
    element = obj.get("blur_element", -1) if element is None else element
    empty = empties.get(element)
    if empty is not None and "blur_matrix" in empty:
        ref = _world(root) @ _matrix(empty["blur_matrix"])
    elif empty is None and placed and element in placed:
        ref = _world(root) @ placed[element]
    else:
        ref = _world(empty if empty is not None else root)
    return ref.inverted_safe() @ _world(obj)


def _nearest(points, targets):
    """For each target point, the number of the nearest of `points` (or 0 if there are none)."""
    if not len(points):
        return np.zeros(len(targets), np.int64)
    tree = kdtree.KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    out = np.empty(len(targets), np.int64)
    cache = {}
    for i, t in enumerate(map(tuple, targets)):
        hit = cache.get(t)
        if hit is None:
            hit = cache[t] = tree.find(t)[1]
        out[i] = hit
    return out


def _unique_rows(rows):
    """(distinct rows in first-seen order, number of each input row among them)."""
    view = np.ascontiguousarray(rows).view(np.dtype((np.void, rows.shape[1])))[:, 0]
    _, first, inverse = np.unique(view, return_index=True, return_inverse=True)
    order = np.argsort(first)
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return rows[first[order]], rank[inverse.ravel()]


class _Mesh:
    """An object's evaluated mesh as numpy arrays (per triangle corner)."""

    def __init__(self, obj, depsgraph, to_element):
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            me.calc_loop_triangles()
            nt, nl, nv = len(me.loop_triangles), len(me.loops), len(me.vertices)
            self.tri_loops = np.empty(nt * 3, np.int32)
            me.loop_triangles.foreach_get("loops", self.tri_loops)
            self.tri_loops = self.tri_loops.reshape(nt, 3)
            self.tri_mat = np.empty(nt, np.int32)
            me.loop_triangles.foreach_get("material_index", self.tri_mat)
            loop_vert = np.empty(nl, np.int32)
            me.loops.foreach_get("vertex_index", loop_vert)
            co = np.empty(nv * 3, np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(nv, 3)
            normals = np.empty(nl * 3, np.float32)
            me.corner_normals.foreach_get("vector", normals)
            normals = normals.reshape(nl, 3)
            m = np.array(to_element, np.float64)
            lin = m[:3, :3]
            pos = co[loop_vert] @ lin.T + m[:3, 3]
            nrm = normals @ np.linalg.inv(lin)          # (M^-1)^T applied to row vectors
            length = np.linalg.norm(nrm, axis=1, keepdims=True)
            nrm = nrm / np.where(length > 0, length, 1.0)
            self.pos = pos[:, [0, 2, 1]].astype(np.float32)        # Blender z-up -> Blur y-up
            self.nrm = nrm[:, [0, 2, 1]].astype(np.float32)
            def read_uv(layer):
                uv = np.empty(nl * 2, np.float32)
                layer.data.foreach_get("uv", uv)
                uv = uv.reshape(nl, 2)
                uv[:, 1] = 1.0 - uv[:, 1]
                return uv

            # sets 1 and 2: the first two maps that aren't a "second pair" map (by name)
            second_names = set(importer.SECOND_UV.values())
            self.uvs = [read_uv(layer) for layer in me.uv_layers if layer.name not in second_names][:2]
            self.second_uvs = {i: read_uv(me.uv_layers[name]) for i, name in importer.SECOND_UV.items()
                               if name in me.uv_layers}
            self.custom_normals = me.has_custom_normals
            self.vertex_id = None
            attr = me.attributes.get(importer.VERTEX_ID)
            if attr is not None and attr.domain == "POINT" and attr.data_type == "INT":
                ids = np.empty(nv, np.int32)
                attr.data.foreach_get("value", ids)
                self.vertex_id = ids[loop_vert]
            self.color = None
            attr = me.color_attributes.get("Color") or me.color_attributes.active_color
            if attr is not None and attr.domain in ("POINT", "CORNER"):
                c = np.empty(len(attr.data) * 4, np.float32)
                attr.data.foreach_get("color", c)
                c = c.reshape(-1, 4)
                self.color = (c[loop_vert] if attr.domain == "POINT" else c)[:, [2, 1, 0, 3]]   # B, G, R, A
        finally:
            ev.to_mesh_clear()


def _encode_where(rows, where, e, values):
    """parts.encode() on the rows picked by the boolean array `where`."""
    if where.all():
        parts.encode(rows, e, values)
    elif where.any():
        sub = rows[where]
        parts.encode(sub, e, values[where])
        rows[where] = sub
    if e.usage == parts.POSITION and e.type == parts.HALF4:
        rows[where, e.offset + 6:e.offset + 8] = 0           # w is 0 in every model


def _encode_slot(sd, part, mesh, slot, name, own=True):
    """(vertex rows, triangles) of the faces in `slot` of `mesh`, in the part's vertex format.
    `own`: the faces belong to `part` (vertices it had keep their data); else `part` is only
    the template of a new part (its vertices lend what Blender doesn't hold)."""
    sel = mesh.tri_mat == slot
    corners = mesh.tri_loops[sel].ravel()
    vb = parts.vertex_buffer(sd.scene, part.vb)
    stride = vb["stride"]
    if not len(corners):
        return np.zeros((0, stride), np.uint8), None
    els = sd.layout(part)
    old = sd.rows(part.vb)[part.base:part.base + part.span]
    pos_el = parts.find(els, parts.POSITION)
    pos = mesh.pos[corners]
    if pos_el is None:
        raise ExportError(f"{name}: the part's vertices have no position")
    old_pos = parts.decode(old, pos_el, 3) if len(old) else np.zeros((0, 3), np.float32)
    # The vertex each corner was imported from, while it hasn't moved
    kept = np.zeros(len(corners), bool)
    source = np.zeros(len(corners), np.int64)
    if own and mesh.vertex_id is not None and len(old):
        vid = mesh.vertex_id[corners].astype(np.int64)
        ok = (vid >= 0) & (vid < len(old))
        source[ok] = vid[ok]
        kept = ok & (np.abs(old_pos[source] - pos).max(axis=1) < 1e-5)
    if len(old):
        moved = ~kept
        if moved.any():
            source[moved] = _nearest(old_pos, pos[moved])
        rows = old[source].copy()
    else:
        rows = np.zeros((len(corners), stride), np.uint8)
    _encode_where(rows, ~kept, pos_el, pos)                 # unmoved vertices keep their exact bytes
    e = parts.find(els, parts.NORMAL)
    if e is not None:
        # Blender has no normal for a zero-area triangle's corners: those keep the old vertex's
        t = pos.reshape(-1, 3, 3)
        area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        flat = np.repeat(area < 1e-7, 3)
        keep = flat | (kept if mesh.custom_normals else np.zeros_like(kept))
        _encode_where(rows, ~keep if len(old) else np.ones_like(keep), e, mesh.nrm[corners])
    for i, uv in enumerate(mesh.uvs):
        e = parts.find(els, parts.TEXCOORD, i)
        if e is not None and e.type in (parts.HALF2, parts.HALF4, parts.FLOAT3, parts.FLOAT4):
            parts.encode(rows, e, uv[corners])
    for i, uv in mesh.second_uvs.items():           # 3rd/4th numbers ("UV On / Dents"...)
        e = parts.find(els, parts.TEXCOORD, i)
        if e is not None and e.type in (parts.HALF4, parts.FLOAT4):
            values = parts.decode(rows, e, 4)
            # only where moved: unused or odd values (NaN) keep their exact bytes
            moved = np.abs(values[:, 2:4] - uv[corners]).max(axis=1) > 1e-5
            values[:, 2:4] = uv[corners]
            _encode_where(rows, moved, e, values)
    e = parts.find(els, parts.COLOR)
    if e is not None and mesh.color is not None:
        colour = mesh.color[corners]
        # Blender's byte colours round: within 1.5/255 of the old colour keeps the old bytes
        repainted = np.abs(colour - parts.decode(rows, e, 4)).max(axis=1) > 1.5 / 255
        _encode_where(rows, repainted, e, colour)
    verts, numbers = _unique_rows(rows)
    if len(verts) > 0xFFFF:
        raise ExportError(f"{name}: {len(verts)} vertices in one part, at most 65535 fit — split it")
    return verts, numbers.reshape(-1, 3)[:, [0, 2, 1]]   # back to Blur's corner order (axes mirrored)




def _signature(rows, tris):
    """One level's triangles as a sorted list of their corners' bytes (each triangle rotated
    to start at its smallest corner, so the winding counts)."""
    if tris is None or not len(tris):
        return []
    out = []
    for a, b, c in np.asarray(tris).tolist():
        t = (rows[a].tobytes(), rows[b].tobytes(), rows[c].tobytes())
        out.append(min(t, t[1:] + t[:1], t[2:] + t[:2]))
    return sorted(out)


def _unchanged(sd, part, vertices, have):
    """True if the levels in Blender (`have`: level -> triangles) draw the part exactly as the
    file does. Levels that weren't imported then keep the file's own too."""
    old = sd.rows(part.vb)[part.base:part.base + part.span]
    for level, tris in have.items():
        if level < len(part.lods) and                 _signature(vertices, tris) != _signature(old, sd.triangles(part, level)):
            return False
    return True


def _imported(root, sd, objects):
    """{part key: detail levels} the importer made meshes for."""
    out = {}
    if "blur_imported" in root:
        for item in str(root["blur_imported"]).split(";"):
            if ":" in item:
                lod, key = item.split(":", 1)
                out.setdefault(key, set()).add(int(lod))
        return out
    # imported before that was recorded: what the importer makes for the levels found
    meshes = [o for o in objects if o.type == "MESH" and "blur_parts" in o]
    levels = {int(o.get("blur_lod", 0)) for o in meshes if not o.get("blur_shadow")}
    shadow_levels = {int(o.get("blur_lod", 0)) for o in meshes if o.get("blur_shadow")}
    for p in sd.parts:
        if p.vb is None:
            continue
        for lod in (shadow_levels if parts.is_shadow(sd.layout(p)) else levels):
            if lod < len(p.lods) and len(sd.triangles(p, lod)):
                out.setdefault(p.key, set()).add(lod)
    return out


def _part_effect(part):
    table = _values_table(part.rl)
    if part.values >= len(table["sets"]):
        return ""
    return part.rl["materials"]["types"][table["sets"][part.values]["type"]]["effect"]


def export_model(context, root, source, out_path):
    """Writes `source` with the edits under `root` to `out_path`; returns (summary, notes)."""
    with open(source, "rb") as fh:
        data = fh.read()
    sd = importer.SceneData(data)
    by_key = {p.key: p for p in sd.parts}
    objects = _model_objects(root)
    empties = {o["blur_element"]: o for o in objects
               if o.type == "EMPTY" and "blur_element" in o and "blur_collision" not in o}
    placed = {i: importer.element_matrix(e)
              for i, e in enumerate(blurmodel.read_elements(data, chunks.parse(data)))}
    for obj in objects:
        if obj.type == "MESH" and obj.mode == "EDIT":
            obj.update_from_editmode()          # edits still in Edit Mode
    depsgraph = context.evaluated_depsgraph_get()
    available = parts.effects_in(sd.scene)

    pieces = {}            # key -> lod -> [(rows, triangles or None)]
    slot_material = {}     # key -> (material, where, level) from the most detailed level seen
    names = {}             # key -> object name, for the report
    new_parts = {}         # (element, effect, material name) -> [template, material, where, [(rows, tris)]]
    removed = set()        # parts drawn with another effect or on another element now (their
                           # faces become a new part), and parts deleted in Blender
    present = {}           # key -> detail levels with a mesh in Blender
    notes = []

    def new_piece(obj, mesh, slot, element, mat, name):
        effect = materials.material_effect(mat) if mat else ""
        if not effect:
            notes.append(f"{name}: no Blur material, skipped (Material Properties > Blur Material)")
            return
        found = parts.templates(sd.scene, effect)
        if not found:
            notes.append(f"{name}: {effect} isn't used anywhere in this model, so it can't be added yet; "
                         f"this model has: {', '.join(e.rsplit('.', 1)[0] for e in available)}")
            return
        template = next((t for t in found if t.element == element), found[0])
        rows, tris = _encode_slot(sd, template, mesh, slot, name, own=False)
        if tris is None:
            return
        entry = new_parts.setdefault((element, effect.lower(), mat.name), [template, mat, name, []])
        entry[3].append((rows, tris))

    for obj in objects:
        if obj.type != "MESH" or "blur_collision" in obj:
            continue
        if "blur_parts" not in obj:
            # a new object: every slot becomes a new part on the element it sits under
            element = element_of(obj, root)
            mesh = _Mesh(obj, depsgraph, _element_space(obj, root, empties, element, placed))
            for slot in sorted(set(np.unique(mesh.tri_mat).tolist())):
                mat = obj.material_slots[slot].material if slot < len(obj.material_slots) else None
                new_piece(obj, mesh, slot, element, mat, f"{obj.name}, slot {slot + 1}")
            continue
        keys = str(obj["blur_parts"]).split(";")
        lod = int(obj.get("blur_lod", 0))
        for key in keys:
            present.setdefault(key, set()).add(lod)
        element = element_of(obj, root)
        to = _parent_element(obj, root)
        if to is not None and element >= 0 and to != element and lod == 0 and not obj.get("blur_shadow"):
            # put under another element's empty: its parts move to that element
            mesh = _Mesh(obj, depsgraph, _element_space(obj, root, empties, to, placed))
            for slot in sorted(set(np.unique(mesh.tri_mat).tolist())):
                mat = obj.material_slots[slot].material if slot < len(obj.material_slots) else None
                new_piece(obj, mesh, slot, to, mat, f"{obj.name}, slot {slot + 1}")
            removed.update(keys)
            continue
        mesh = _Mesh(obj, depsgraph, _element_space(obj, root, empties, None, placed))
        for slot in sorted(set(np.unique(mesh.tri_mat).tolist()) - set(range(len(keys)))):
            # a slot added in Blender: a new part (most detailed level only)
            mat = obj.material_slots[slot].material if slot < len(obj.material_slots) else None
            if lod == 0:
                new_piece(obj, mesh, slot, element, mat, f"{obj.name}, slot {slot + 1}")
        for slot, key in enumerate(keys):
            part = by_key.get(key)
            if part is None:
                notes.append(f"{obj.name}: slot {slot + 1} names part {key}, which the model doesn't have")
                continue
            name = f"{obj.name}, slot {slot + 1}"
            mat = obj.material_slots[slot].material if slot < len(obj.material_slots) else None
            effect = materials.material_effect(mat) if mat else ""
            if effect and effect.lower() != _part_effect(part).lower() and _part_effect(part):
                # drawn with another effect now: the faces become a new part, the old one goes
                if lod == 0:
                    removed.add(key)
                    new_piece(obj, mesh, slot, part.element, mat, name)
                continue
            pieces.setdefault(key, {}).setdefault(lod, []).append(_encode_slot(sd, part, mesh, slot, name))
            if key not in slot_material or lod < slot_material[key][2]:
                slot_material[key] = (mat, name, lod)
            names.setdefault(key, re.sub(r"( LOD\d+)?(\.\d+)?$", "", obj.name))

    # parts the importer made a mesh for that isn't there any more: deleted in Blender
    deleted = []
    for key, levels in _imported(root, sd, objects).items():
        if key not in by_key or key in removed:
            continue
        have = present.get(key, set())
        if not have:
            removed.add(key)
            deleted.append(key)
        else:
            for lod in levels - have:
                pieces.setdefault(key, {})[lod] = []        # that level's mesh was deleted

    edits = {}
    for key, levels in pieces.items():
        if key in removed:
            continue
        part = by_key[key]
        rows, lods, have = [], [], {}
        at = 0
        for level, items in sorted(levels.items()):
            tris = []
            for r, t in items:
                if t is not None:
                    tris.append(t + at)
                rows.append(r)
                at += len(r)
            have[level] = np.concatenate(tris) if tris else None
        for level, (start, count, lo, n) in enumerate(part.lods):
            if level in have:
                lods.append(have[level])
            elif not count:
                lods.append(None)
            else:
                better = [lv for lv in have if lv < level]
                lods.append(have[max(better)] if better else have[min(have)])
        stride = parts.vertex_buffer(sd.scene, part.vb)["stride"]
        vertices = np.concatenate(rows) if rows else np.zeros((0, stride), np.uint8)
        if len(vertices) > 0xFFFF:
            raise ExportError(f"part {key}: {len(vertices)} vertices over its detail levels, at most 65535 fit")
        if not _unchanged(sd, part, vertices, have):
            edits[key] = parts.Edit(vertices, lods)   # parts drawn as before keep their bytes

    model_path = root.get("blur_model", "")
    new_textures = {}
    changed_sets = _apply_materials(sd, by_key, slot_material, model_path, notes, new_textures)
    try:
        # removed parts are rebuilt empty: their vertices and indices leave the buffers (a gap
        # left behind isn't how the game's files look, and 26Viewer can't read past one)
        emptied = {}
        for key in removed:
            part = by_key[key]
            if part.vb is not None:
                stride = parts.vertex_buffer(sd.scene, part.vb)["stride"]
                emptied[key] = parts.Edit(np.zeros((0, stride), np.uint8), [None])
        parts.rebuild(sd.scene, {**edits, **emptied})
        for key in removed:
            if key not in emptied:
                parts.remove_part(by_key[key])
        # new parts last: adding one renumbers the parts drawn after it
        made = []
        for (element, _effect, _mat), (template, mat, where, items) in new_parts.items():
            rows, tris, at = [], [], 0
            for r, t in items:
                rows.append(r)
                tris.append(t + at)
                at += len(r)
            current = next(p for p in parts.parts(sd.scene) if p.record is template.record)
            record = parts.add_part(sd.scene, current, element, np.concatenate(rows), [np.concatenate(tris)])
            made.append((record, mat, where))
        now = parts.parts(sd.scene)
        for record, mat, where in made:
            part = next(p for p in now if p.record is record)
            _apply_materials(sd, {part.key: part}, {part.key: (mat, where, 0)}, model_path, notes, new_textures)
        out = chunks.replace_payload(data, sd.path, scene.write(sd.scene))
        coll_payload, coll_summary = _export_collision(data, root, objects, depsgraph, notes)
        if coll_payload is not None:
            out = chunks.replace_payload(out, chunks.find_path(chunks.parse(out), "Coll"), coll_payload)
    except (parts.PartsError, scene.SceneError, collision.CollisionError) as e:
        raise ExportError(str(e)) from e
    with open(out_path, "wb") as fh:
        fh.write(out)
    changed = sorted({names.get(k, k) for k in edits})
    shown = ", ".join(changed[:6]) + ("…" if len(changed) > 6 else "")
    gone = sorted({_deleted_name(by_key[k], root) for k in deleted})
    summary = (f"geometry of {len(edits)} part(s) changed" + (f" ({shown})" if changed else "")
               + (f"; {len(deleted)} part(s) removed ({', '.join(gone[:6])}{'…' if len(gone) > 6 else ''})"
                  if deleted else "")
               + (f"; {len(made)} new part(s)" if made else "")
               + (f"; {len(removed) - len(deleted)} part(s) moved to another effect or element"
                  if len(removed) > len(deleted) else "")
               + f"; {changed_sets} material(s) changed; {len(new_textures)} new texture(s)"
               + (f"; collision: {coll_summary}" if coll_summary else ""))
    return summary, notes


def _deleted_name(part, root):
    """A readable name for a deleted part: its element's empty, if that's still there."""
    for o in root.children_recursive:
        if o.type == "EMPTY" and o.get("blur_element") == part.element and "blur_collision" not in o:
            return o.name
    return part.key


# ---- collision ------------------------------------------------------------------------------------

def _close(a, b, tol=1e-5):
    a = [v for row in a for v in row]
    b = [v for row in b for v in row]
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def _hull(points):
    """(vertices, triangles) of the convex hull of `points` (Blur axes), triangles facing out."""
    bm = bmesh.new()
    try:
        for p in points:
            bm.verts.new(p)
        res = bmesh.ops.convex_hull(bm, input=bm.verts[:], use_existing_faces=False)
        drop = [v for v in res["geom_interior"] + res["geom_unused"] if isinstance(v, bmesh.types.BMVert)]
        if drop:
            bmesh.ops.delete(bm, geom=drop, context="VERTS")
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.verts.index_update()
        verts = [tuple(v.co) for v in bm.verts]
        tris = [[v.index for v in f.verts] for f in bm.faces]
    finally:
        bm.free()
    if len(verts) < 4 or not tris:
        return None, None
    v = np.array(verts)
    centre = v.mean(axis=0)
    out = []
    for a, b, c in tris:
        n = np.cross(v[b] - v[a], v[c] - v[a])
        out.append((a, b, c) if np.dot(n, (v[a] + v[b] + v[c]) / 3 - centre) >= 0 else (a, c, b))
    return verts, out


def _export_collision(data, root, objects, depsgraph, notes):
    """(the Coll chunk's new payload or None, summary) for the collision edits in Blender:
    convex hulls edited, moved or deleted, bodies moved."""
    path = chunks.find_path(chunks.parse(data), "Coll")
    if not path:
        return None, ""
    in_blender = [o for o in objects if "blur_collision" in o]
    if "blur_shapes" not in root:
        if in_blender:
            notes.append("collision: this model was imported before collision export existed, so collision "
                         "edits aren't written; import it again to edit its collision")
        return None, ""
    c = path[-1]
    start, end = c.payload_offset, c.offset + c.size
    stream = collision.read(data, start, end)
    shapes = {}
    for i, o in enumerate(stream):
        shapes[str(i)] = (o, None)
        for j, child in enumerate(o.get("shapes", [])):
            shapes[f"{i}.{j}"] = (child, o)
    present = {str(o["blur_shape"]): o for o in in_blender if "blur_shape" in o}
    changes, edited, moved, gone = [], 0, 0, {}
    for sid in str(root["blur_shapes"]).split(";"):
        if sid not in shapes:
            continue
        shape, body = shapes[sid]
        obj = present.get(sid)
        kind = collision.TYPE_NAMES.get(shape["type"], str(shape["type"]))
        if obj is None:
            if body is not None and body["type"] == 7:
                gone.setdefault(id(body), [body, []])[1].append(shape)
            else:
                notes.append(f"collision object {sid} ({kind}): deleting a whole collision object "
                             "isn't supported (delete the shapes inside it), kept")
            continue
        local = obj.matrix_parent_inverse @ obj.matrix_basis
        orig = _matrix(obj["blur_matrix"]) if "blur_matrix" in obj else local
        if shape["type"] == 3 and obj.type == "MESH":
            ev = obj.evaluated_get(depsgraph)
            me = ev.to_mesh()
            try:
                to_shape = orig.inverted_safe() @ local
                pts = [tuple(to_shape @ v.co) for v in me.vertices]
            finally:
                ev.to_mesh_clear()
            pts = [(x, z, y) for x, y, z in pts]                   # Blender z-up -> Blur y-up
            if _close(pts, shape["vertices"]):
                continue
            if obj.get("blur_copy"):
                notes.append(f"{obj.name}: a placed copy of a shared collision shape, edits not written")
                continue
            verts, tris = _hull(pts)
            if verts is None:
                notes.append(f"{obj.name}: a convex hull needs at least 4 points that aren't flat, kept")
                continue
            changes.append((shape["_hull"], shape["_hull_end"], collision.hull_bytes(verts, tris)))
            edited += 1
        elif body is None and not _close(local, orig):
            # a top-level object moved: its placement (its space starts at position + centre)
            m = importer.SWAP @ local @ importer.SWAP
            loc, rot, scale = m.decompose()
            if any(abs(x - 1.0) > 1e-4 for x in scale):
                notes.append(f"{obj.name}: collision objects can't be scaled, only the move and turn are written")
            r = rot.to_matrix()
            rotation = [r[i][j] for j in range(3) for i in range(3)]   # rotation[3j + i] = m[i][j]
            position = [loc[k] - shape["centre"][k] for k in range(3)]
            p = shape["_place"]
            changes.append((p, p + 48, struct.pack("<12f", *position, *rotation)))
            moved += 1
        elif obj.type == "MESH" and shape["type"] != 3:
            if not _close(local, orig) or len(obj.data.vertices) != len(shape.get("vertices") or []):
                notes.append(f"{obj.name}: editing {kind} collision shapes isn't supported yet, kept")
        elif not _close(local, orig):
            notes.append(f"{obj.name}: moving {kind} collision shapes isn't supported yet, kept")
    removed = 0
    for body, lost in gone.values():
        left = len(body["shapes"]) - len(lost)
        if left < 1:
            notes.append("collision: a body keeps at least one shape (deleting all of them isn't supported)")
            continue
        for shape in lost:
            changes.append((shape["_at"], shape["_end"], b""))
        changes.append((body["_count"], body["_count"] + 4, struct.pack("<I", left)))
        removed += len(lost)
    if not changes:
        return None, ""
    bits = [f"{edited} hull(s) changed" if edited else "", f"{moved} object(s) moved" if moved else "",
            f"{removed} shape(s) removed" if removed else ""]
    return collision.write(data, start, end, changes), ", ".join(b for b in bits if b)


# ---- materials -------------------------------------------------------------------------------------

_INT = {0: "<b", 1: "<B", 2: "<h", 3: "<H", 4: "<i", 5: "<I"}


def _values_table(rl):
    return rl["values"] if "values" in rl else rl["materials"]["values"]


def _texture_entry(source):
    """"k:3" / "p:5:0" -> the render list texture table's (package, index) pair."""
    bits = source.split(":")
    if bits[0] == "k":
        return [0xFFFFFFFF, int(bits[1])]
    return [int(bits[1]), int(bits[2])]


def _picture(img):
    """(format, width, height, mips, pixels) to store for an image: a .dds with mipmaps as it
    is; any other picture (and a .dds without mipmaps: the game's textures always have them,
    without them a texture shimmers at a distance) compressed to DXT1 (DXT5 if it has
    transparency) with a full mip chain."""
    raw = None
    if img.packed_file is not None:
        raw = bytes(img.packed_file.data)
    elif img.filepath:
        try:
            with open(bpy.path.abspath(img.filepath), "rb") as fh:
                raw = fh.read()
        except OSError:
            raw = None
    if raw and raw[:4] == b"DDS ":
        got = dds.read(raw)
        if got is not None and (got[3] > 1 or max(got[1], got[2]) <= 4):
            return got
    w, h = img.size
    if not w or not h:
        raise ExportError(f"image {img.name} has no pixels (is its file missing?)")
    pw, ph = 1 << (w - 1).bit_length(), 1 << (h - 1).bit_length()
    src = img
    if (pw, ph) != (w, h):              # Blur's textures are powers of two
        src = img.copy()
        src.scale(pw, ph)
    px = np.empty(pw * ph * 4, np.float32)
    src.pixels.foreach_get(px)
    if src is not img:
        bpy.data.images.remove(src)
    rgba = np.clip(np.rint(px.reshape(ph, pw, 4)[::-1] * 255), 0, 255).astype(np.uint8)   # top row first
    code, mips, data = textures.compress(rgba, bool((rgba[..., 3] < 250).any()))
    return code, pw, ph, mips, data


def _apply_materials(sd, by_key, slot_material, model_path, notes, new_textures):
    """Writes the Blender materials' numbers and textures into the parts' material values
    (`new_textures`: image name -> keyed texture number, shared between calls). Returns the
    number of value sets changed."""
    written = {}           # (render list, value set) -> material name
    changed = 0
    # parts sharing one value set: the material most of them have keeps it, the others get a copy
    users = {}
    for key, (mat, _where, _lod) in slot_material.items():
        part = by_key[key]
        if mat is not None:
            users.setdefault((id(part.rl), part.values), []).append(mat.name)
    owner = {k: max(names, key=names.count) for k, names in users.items()}
    order = sorted(slot_material.items(),
                   key=lambda kv: (kv[1][0] is None or owner.get((id(by_key[kv[0]].rl), by_key[kv[0]].values))
                                   != kv[1][0].name, kv[0]))
    for key, (mat, where, _lod) in order:
        part = by_key[key]
        if mat is None:
            continue
        table = _values_table(part.rl)
        if part.values >= len(table["sets"]):
            continue
        vs = table["sets"][part.values]
        mt = part.rl["materials"]["types"][vs["type"]]
        if not mt["effect"]:
            continue                       # shadow hulls and other unnamed entries
        effect = materials.material_effect(mat)
        node = materials.group_node(mat)
        if not effect or node is None:
            notes.append(f"{where}: {mat.name} isn't a Blur material, the part keeps its own")
            continue
        if effect.lower() != mt["effect"].lower():
            notes.append(f"{where}: {mat.name} uses {effect} but the part is drawn with {mt['effect']}; "
                         "changing a part's effect isn't supported yet, it keeps its own")
            continue
        slot_id = (id(part.rl), part.values)
        if slot_id in written:
            if written[slot_id] == mat.name:
                continue
            # shared with a part that has another material now: this part gets its own values
            vs = copy.deepcopy(vs)
            table["sets"].append(vs)
            table["total"] += mt["size"]
            part.record["streams"][0]["buffer"]["a"] = len(table["sets"]) - 1
            slot_id = (id(part.rl), part.values)
        written[slot_id] = mat.name
        if not mt["size"]:
            continue
        values, i, dirty = list(vs["values"]), 0, False
        for el in mt["elements"]:
            sockets = materials.number_sockets(el["name"], el["count"])
            for c in range(el["count"]):
                old = new = values[i]
                if el["type"] == 6 and sockets[c] in node.inputs:
                    new = struct.pack("<f", float(node.inputs[sockets[c]].default_value))
                    if struct.unpack("<f", new)[0] == struct.unpack("<f", old)[0]:
                        new = old
                elif el["type"] in _INT and sockets[c] in node.inputs:
                    try:
                        new = struct.pack(_INT[el["type"]], int(node.inputs[sockets[c]].default_value))
                    except struct.error:
                        notes.append(f"{where}: {sockets[c]} is out of range, kept")
                elif el["type"] == 7 and c == 0:
                    new = _texture_value(sd, part, mat, el["name"], old, model_path, new_textures, where, notes)
                if new != old:
                    values[i] = new
                    dirty = True
                i += 1
        if dirty:
            vs["values"] = values
            changed += 1
    return changed


def _texture_value(sd, part, mat, input_name, old, model_path, new_textures, where, notes):
    """The TEXTURE_INDEX bytes for the image in one of a material's texture slots."""
    tex = mat.node_tree.nodes.get(input_name)
    img = tex.image if tex is not None and tex.type == "TEX_IMAGE" else None
    if img is None:
        return old
    items = part.rl["textures"]["items"]
    current = struct.unpack("<I", old)[0]
    if img.get("blur_source") and img.get("blur_model_path", model_path) == model_path:
        entry = _texture_entry(str(img["blur_source"]))
    else:
        if img.name not in new_textures:
            colour = materials.texture_role(input_name) in ("color", "emission")
            code, w, h, mips, pixels = _picture(img)
            if code not in dds.FORMATS:
                raise ExportError(f"{where}: {img.name} is in a format Blur can't use")
            new_textures[img.name] = textures.add_keyed(sd.scene, img.name, code, w, h, mips, pixels, colour)
            notes.append(f"{img.name}: added to the model as {dds.name(code)}, {w}x{h}, {mips} mip levels")
        entry = [0xFFFFFFFF, new_textures[img.name]]
    if current < len(items) and list(items[current]) == entry:
        return old
    for i, e in enumerate(items):
        if list(e) == entry:
            return struct.pack("<I", i)
    items.append(entry)
    return struct.pack("<I", len(items) - 1)
