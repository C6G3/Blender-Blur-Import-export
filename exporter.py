"""Writes an imported Blur model back with the edits made in Blender.

The model's own file is the starting point (its path is on the root empty,
"blur_model"): every mesh made by the importer names the part behind each of
its material slots ("blur_parts"), so the faces of a slot become that part's
new geometry. Parts whose mesh isn't in Blender (not imported, or the object
was deleted) keep their old geometry. A slot with no faces left removes that
part (it stops being drawn).

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
use stay unused.
"""

import numpy as np
from mathutils import kdtree

from . import importer
from .blur import chunks, parts, scene


class ExportError(Exception):
    pass


def model_root(obj):
    """The importer's root empty above `obj` (or `obj` itself), or None."""
    while obj is not None:
        if "blur_model" in obj:
            return obj
        obj = obj.parent
    return None


def _descendants(root):
    return [o for o in root.children_recursive]


def _world(obj):
    """The object's placement from its parent chain. (matrix_world isn't kept up to date for
    objects in excluded collections, such as the hidden detail levels.)"""
    m = obj.matrix_parent_inverse @ obj.matrix_basis
    return _world(obj.parent) @ m if obj.parent is not None else m


def _element_space(obj, root, empties):
    """Matrix from the object's local space into its Blur element's space."""
    element = obj.get("blur_element", -1)
    empty = empties.get(element)
    ref = empty if empty is not None else root
    return _world(ref).inverted_safe() @ _world(obj)


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
            self.uvs = []
            for layer in list(me.uv_layers)[:2]:
                uv = np.empty(nl * 2, np.float32)
                layer.data.foreach_get("uv", uv)
                uv = uv.reshape(nl, 2)
                uv[:, 1] = 1.0 - uv[:, 1]
                self.uvs.append(uv)
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


def _encode_slot(sd, part, mesh, slot, name):
    """(vertex rows, triangles) of the faces in `slot` of `mesh`, in the part's vertex format."""
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
    if mesh.vertex_id is not None and len(old):
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
    e = parts.find(els, parts.COLOR)
    if e is not None and mesh.color is not None:
        parts.encode(rows, e, mesh.color[corners])
    verts, numbers = _unique_rows(rows)
    if len(verts) > 0xFFFF:
        raise ExportError(f"{name}: {len(verts)} vertices in one part, at most 65535 fit — split it")
    return verts, numbers.reshape(-1, 3)[:, [0, 2, 1]]   # back to Blur's corner order (axes mirrored)


def export_model(context, root, source, out_path):
    """Writes `source` with the edits under `root` to `out_path`; returns notes for the user."""
    with open(source, "rb") as fh:
        data = fh.read()
    sd = importer.SceneData(data)
    by_key = {p.key: p for p in sd.parts}
    objects = _descendants(root)
    empties = {o["blur_element"]: o for o in objects if o.type == "EMPTY" and "blur_element" in o}
    depsgraph = context.evaluated_depsgraph_get()

    pieces = {}            # key -> lod -> [(rows, triangles or None)]
    notes = []
    for obj in objects:
        if obj.type != "MESH" or "blur_parts" not in obj:
            if obj.type == "MESH":
                notes.append(f"{obj.name}: not from the imported model, skipped (new parts aren't supported yet)")
            continue
        keys = str(obj["blur_parts"]).split(";")
        lod = int(obj.get("blur_lod", 0))
        mesh = _Mesh(obj, depsgraph, _element_space(obj, root, empties))
        extra = set(np.unique(mesh.tri_mat).tolist()) - set(range(len(keys)))
        if extra:
            notes.append(f"{obj.name}: faces in material slot(s) {sorted(i + 1 for i in extra)} skipped "
                         "(slots added in Blender have no Blur part yet)")
        for slot, key in enumerate(keys):
            part = by_key.get(key)
            if part is None:
                notes.append(f"{obj.name}: slot {slot + 1} names part {key}, which the model doesn't have")
                continue
            name = f"{obj.name}, slot {slot + 1}"
            pieces.setdefault(key, {}).setdefault(lod, []).append(_encode_slot(sd, part, mesh, slot, name))

    edits = {}
    for key, levels in pieces.items():
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
        edits[key] = parts.Edit(vertices, lods)

    try:
        parts.rebuild(sd.scene, edits)
        out = chunks.replace_payload(data, sd.path, scene.write(sd.scene))
    except (parts.PartsError, scene.SceneError) as e:
        raise ExportError(str(e)) from e
    with open(out_path, "wb") as fh:
        fh.write(out)
    return len(edits), notes

