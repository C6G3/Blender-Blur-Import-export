"""Builds Blender objects from a Blur .model file.

Layout in the scene:

    <model> (empty, the file)                     collection "<model>"
      e_exterior (empty, a MdlDat element)
        e_exterior (mesh: the element's parts at detail level 0, one material slot each)
        e_door_left (empty) > e_door_left (mesh) ...
    collections "<model> LOD1".. hold lower detail levels, "<model> Shadow" the
    shadow hulls (hidden)

Coordinates: Blur is Direct3D (left-handed, x right, y up, z forward); Blender
is right-handed z-up, so (x, y, z) -> (x, z, y). Swapping two axes mirrors the
model, so every triangle's corner order is reversed too (faces point out, as
their normals do: checked against the stored normals).
Mesh vertices stay in their element's own space; the element empties carry the
placement (MdlDat rotation and position), so parts move like in the game.

Geometry comes from the scene stream (blur.scene / blur.parts): every material
slot of a mesh is one part (geometry record) of the model, named in the
object's "blur_parts" property (part keys in slot order), which is how the
exporter puts edited meshes back. Materials (each part's effect and material
values) and textures come from the scene stream too; part names and placement
from MdlDat's element table.
"""

import colorsys
import os
import struct
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

from . import materials
from .blur import chunks, collision, dds, parts, scene, textures
from .blur import model as blurmodel


SWAP = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def element_matrix(e):
    r, t = e.rotation, e.position
    # row vectors p' = p R + t  ->  column form [[R^T, t], [0, 1]], then into Blender axes
    m = Matrix(((r[0], r[3], r[6], t[0]), (r[1], r[4], r[7], t[1]), (r[2], r[5], r[8], t[2]), (0, 0, 0, 1)))
    return SWAP @ m @ SWAP


# ---- textures ------------------------------------------------------------------------------

def load_textures(stored, model_path, folder):
    """Every texture the model holds (blur.textures.stored) as a Blender image, keyed by where
    it is stored ("k:3", "p:5:0"); written as .dds into `folder`, loaded and packed."""
    images = {}
    os.makedirs(folder, exist_ok=True)
    for i, t in enumerate(stored):
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in t.name) or f"texture_{i + 1}"
        path = os.path.join(folder, f"{safe}_{i + 1}.dds")
        with open(path, "wb") as fh:
            fh.write(dds.write(t.format, t.width, t.height, t.mip_count, t.pixels))
        try:
            img = bpy.data.images.load(path, check_existing=False)
            img.name = t.name or safe
            img.pack()
            img.filepath = ""  # packed: the temporary file isn't needed any more
        except RuntimeError:
            img = None
        try:
            os.remove(path)
        except OSError:
            pass
        if img is not None:
            img["blur_texture"] = t.name
            img["blur_format"] = dds.name(t.format)
            img["blur_streamed"] = t.streamed
            img["blur_source"] = t.source       # which stored texture this is (for the exporter)
            img["blur_model_path"] = model_path
            images[t.source] = img
    return images


# ---- materials -----------------------------------------------------------------------------

def _values_table(rl):
    return rl["values"] if "values" in rl else rl["materials"]["values"]


_NUMBER = {6: "<f", 0: "<b", 1: "<B", 2: "<h", 3: "<H", 4: "<i", 5: "<I"}


def part_material_values(part):
    """(effect, {texture input: (package, index) entry}, {number input: [values]}) of a part's
    main pass, read from its render list's material value set."""
    table = _values_table(part.rl)
    if part.values >= len(table["sets"]):
        return "", {}, {}
    vs = table["sets"][part.values]
    mt = part.rl["materials"]["types"][vs["type"]]
    tex, numbers = {}, {}
    i = 0
    vals = vs["values"]
    if mt["size"]:
        for el in mt["elements"]:
            got = []
            for _ in range(el["count"]):
                v = vals[i] if i < len(vals) else None
                i += 1
                if isinstance(v, bytes) and el["type"] in _NUMBER:
                    got.append(struct.unpack(_NUMBER[el["type"]], v)[0])
                elif isinstance(v, bytes) and el["type"] == 7:
                    n = struct.unpack("<I", v)[0]
                    items = part.rl["textures"]["items"]
                    if n < len(items):
                        tex[el["name"]] = tuple(items[n])
            if got:
                numbers[el["name"]] = got
    return mt["effect"], tex, numbers


def _source(entry):
    package, index = entry
    return f"k:{index}" if package == parts.NULL else f"p:{package}:{index}"


def part_materials(sd, images, model_name):
    """part key -> Blender material: one per distinct (effect, textures, numbers)."""
    by_key, out = {}, {}
    for p in sd.parts:
        effect, tex, numbers = part_material_values(p)
        if not effect:
            continue
        slots = {name: images.get(_source(entry)) for name, entry in tex.items()}
        key = (effect.lower(), tuple(sorted((k, v.name if v else "") for k, v in slots.items())),
               tuple(sorted((k, tuple(round(x, 6) if isinstance(x, float) else x for x in v))
                            for k, v in numbers.items())))
        if key not in by_key:
            base = effect.rsplit(".", 1)[0]
            colour = next((img.name for k, img in slots.items() if img and materials.texture_role(k) == "color"),
                          None)
            by_key[key] = materials.new_material(effect, f"{model_name} {base}" + (f" {colour}" if colour else ""),
                                                 slots, numbers)
        out[p.key] = by_key[key]
    return out


# ---- meshes --------------------------------------------------------------------------------

VERTEX_ID = "blur_vertex"


class SceneData:
    """The model's scene stream and its parts, with decoded buffers cached."""

    def __init__(self, data):
        root = chunks.parse(data)
        path = chunks.find_path(root, "Scene") if root else []
        if not path:
            raise blurmodel.ModelError("no Render/Scene chunk")
        try:
            self.scene = scene.read(data, path[-1].payload_offset, path[-1].offset + path[-1].size)
        except scene.SceneError as e:
            raise blurmodel.ModelError(f"scene stream: {e}") from e
        self.path = path
        self.parts = [p for p in parts.parts(self.scene) if p.vb is not None]
        self._rows, self._indices = {}, {}

    def rows(self, ref):
        if ref not in self._rows:
            self._rows[ref] = parts.rows(parts.vertex_buffer(self.scene, ref))
        return self._rows[ref]

    def indices(self, ref):
        if ref not in self._indices:
            self._indices[ref] = np.frombuffer(parts.index_buffer(self.scene, ref)["blob"]["data"], np.uint16)
        return self._indices[ref]

    def layout(self, part):
        return parts.layout(parts.vertex_buffer(self.scene, part.vb))

    def triangles(self, part, lod):
        """Triangles of a part at a detail level, numbered from the part's first vertex."""
        if lod >= len(part.lods) or not part.lods[lod][1]:
            return np.zeros((0, 3), np.int64)
        start, count = part.lods[lod][:2]
        return parts.strip_triangles(self.indices(part.ib)[start:start + count])


def attribute(rows, elements, usage, index, components):
    e = parts.find(elements, usage, index)
    if e is None or (usage == parts.TEXCOORD and e.type not in (parts.HALF2, parts.HALF4, parts.FLOAT3,
                                                                     parts.FLOAT4)):
        return None
    return parts.decode(rows, e, components)


def _separate_duplicates(used, tris):
    """Blender keeps one face per set of vertices: a triangle drawn twice on the same vertices
    (both sides of a thin part) gets its own copies of them. The exporter merges equal
    vertices again."""
    _, first = np.unique(np.sort(tris, axis=1), axis=0, return_index=True)
    dup = np.ones(len(tris), bool)
    dup[first] = False
    if not dup.any():
        return used, tris
    tris = tris.copy()
    src = tris[dup].ravel()
    tris[dup] = (len(used) + np.arange(len(src))).reshape(-1, 3)
    return np.concatenate([used, used[src]]), tris


def build_mesh(sd, name, items, mats):
    """A mesh of `items` [(part, lod)], all in one element's space, one material slot per part.
    Returns (mesh, part keys in slot order) or (None, [])."""
    verts, norms, uv0, uv1, cols, faces, face_mat, keys, ids = [], [], [], [], [], [], [], [], []
    total = 0
    for p, lod in items:
        tri = sd.triangles(p, lod)
        if not len(tri):
            continue
        used, remap = np.unique(tri, return_inverse=True)
        remap = remap.reshape(-1, 3)
        used, remap = _separate_duplicates(used, remap)
        rows = sd.rows(p.vb)[p.base + used]
        els = sd.layout(p)
        pos = attribute(rows, els, parts.POSITION, 0, 3)
        nrm = attribute(rows, els, parts.NORMAL, 0, 3)
        verts.append(pos[:, [0, 2, 1]])
        norms.append(nrm[:, [0, 2, 1]] if nrm is not None else np.zeros((len(used), 3), np.float32))
        uv0.append(attribute(rows, els, parts.TEXCOORD, 0, 2))
        uv1.append(attribute(rows, els, parts.TEXCOORD, 1, 2))
        cols.append(attribute(rows, els, parts.COLOR, 0, 4))
        faces.append(remap[:, [0, 2, 1]] + total)   # mirrored axes: reverse the corner order
        ids.append(used)
        face_mat.append(np.full(len(tri), len(keys), np.int32))
        keys.append(p)
        total += len(used)
    if not faces:
        return None, []
    mesh = bpy.data.meshes.new(name)
    for p in keys:
        mesh.materials.append(mats.get(p.key))
    v = np.concatenate(verts).astype(np.float32)
    f = np.concatenate(faces).astype(np.int32)
    mesh.vertices.add(len(v))
    mesh.vertices.foreach_set("co", v.ravel())
    mesh.loops.add(f.size)
    mesh.loops.foreach_set("vertex_index", f.ravel())
    mesh.polygons.add(len(f))
    mesh.polygons.foreach_set("loop_start", np.arange(0, f.size, 3, dtype=np.int32))
    mesh.polygons.foreach_set("material_index", np.concatenate(face_mat))
    mesh.update(calc_edges=True)
    mesh.validate(clean_customdata=False)

    loops = f.ravel()
    n = np.concatenate(norms)
    lengths = np.linalg.norm(n, axis=1)
    if lengths.any():
        n = n / np.where(lengths[:, None] > 0, lengths[:, None], 1.0)
        mesh.normals_split_custom_set_from_vertices([tuple(x) for x in n])
    for layer_name, layer in (("UVMap", uv0), ("UVMap.001", uv1)):
        if all(a is None for a in layer) and layer_name != "UVMap":
            continue
        data = np.concatenate([a if a is not None else np.zeros((len(vv), 2), np.float32)
                               for a, vv in zip(layer, verts)])
        uv = data[loops].copy()
        uv[:, 1] = 1.0 - uv[:, 1]  # Direct3D's v runs down the picture
        layer_ = mesh.uv_layers.new(name=layer_name)
        layer_.data.foreach_set("uv", uv.ravel())
    if all(c is not None for c in cols):
        c = np.concatenate(cols)
        attr = mesh.color_attributes.new("Color", "BYTE_COLOR", "POINT")
        attr.data.foreach_set("color", c[:, [2, 1, 0, 3]].ravel())  # stored B, G, R, A
    # Which vertex of its part each one was: the exporter keeps what Blender doesn't show
    # (damage offsets, bone weights) and, for vertices left in place, the exact normal.
    attr = mesh.attributes.new(VERTEX_ID, "INT", "POINT")
    attr.data.foreach_set("value", np.concatenate(ids).astype(np.int32))
    return mesh, [p.key for p in keys]


# ---- collision -----------------------------------------------------------------------------

def _placement(rotation, position):
    """Blender matrix of a Blur placement (p' = p * R + position, Direct3D axes)."""
    r, t = rotation, position
    m = Matrix(((r[0], r[3], r[6], t[0]), (r[1], r[4], r[7], t[1]), (r[2], r[5], r[8], t[2]), (0, 0, 0, 1)))
    return SWAP @ m @ SWAP


def _surface_material(name):
    """A plain viewport material per collision surface (Tarmac, Metal, Glass...)."""
    full = f"Blur collision: {name}"
    mat = bpy.data.materials.get(full)
    if mat is None:
        mat = bpy.data.materials.new(full)
        h = (hash(name) % 1000) / 1000.0
        mat.diffuse_color = (*colorsys.hsv_to_rgb(h, 0.6, 0.9), 0.6)
        mat["blur_surface"] = name
    return mat


def _shape_mesh(shape, name):
    """A mesh for one collision shape, in its own space (Blender axes)."""
    t = shape["type"]
    bm = bmesh.new()
    if "vertices" in shape:
        verts = [bm.verts.new((v[0], v[2], v[1])) for v in shape["vertices"]]
        bm.verts.ensure_lookup_table()
        surfaces = shape.get("surfaces") or [shape.get("material", 0)] * len(shape["triangles"])
        names = []
        for (a, b, c), surf in zip(shape["triangles"], surfaces):
            if len({a, b, c}) < 3 or max(a, b, c) >= len(verts):
                continue
            try:
                f = bm.faces.new((verts[a], verts[c], verts[b]))   # mirrored axes: reverse the corners
            except ValueError:
                continue                                          # the same triangle twice
            label = collision.surface_name(surf)
            if label not in names:
                names.append(label)
            f.material_index = names.index(label)
    else:
        names = [collision.surface_name(shape.get("material", 0))]
        if t == 2:
            hx, hy, hz = shape["half"]
            bmesh.ops.create_cube(bm, size=2.0)
            bmesh.ops.scale(bm, vec=(hx, hz, hy), verts=bm.verts)
        elif t == 4:
            bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=max(shape["radius"], 1e-4))
        elif t in (5, 6, 15):
            h, rad = max(shape["height"], 1e-4), max(shape["radius"], 1e-4)
            if t == 15:
                bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=rad, radius2=0.0, depth=h)
            else:
                bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=rad, radius2=rad, depth=h)
            if t == 5:   # capsule: round the ends
                for z in (h / 2, -h / 2):
                    ret = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=rad)
                    bmesh.ops.translate(bm, vec=(0, 0, z), verts=ret["verts"])
        else:
            bm.free()
            return None
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for label in names:
        mesh.materials.append(_surface_material(label))
    return mesh


def import_collision(data, elements, model_name, parent_coll, root):
    """The model's Coll chunk as objects in a "<model> Collision" collection. Returns the
    collection (None if the model has none) and notes."""
    path = chunks.find_path(chunks.parse(data), "Coll")
    if not path:
        return None, []
    c = path[-1]
    try:
        objects = collision.read(data, c.payload_offset, c.offset + c.size)
    except collision.CollisionError as e:
        return None, [f"collision not read: {e}"]
    if not objects:
        return None, []
    coll = bpy.data.collections.new(f"{model_name} Collision")
    parent_coll.children.link(coll)
    by_tag = {e.tag: e.name for e in elements if e.tag not in (0, 0xFFFFFFFF)}
    templates = {}

    def label(shape):
        el = by_tag.get(shape["handle"])
        kind = collision.TYPE_NAMES.get(shape["type"], f"type {shape['type']}")
        return f"COL {el} {kind}" if el else f"COL {kind}"

    def add(shape, matrix, parent):
        mesh = _shape_mesh(shape, label(shape))
        obj = bpy.data.objects.new(label(shape), mesh)
        obj["blur_collision"] = collision.TYPE_NAMES.get(shape["type"], str(shape["type"]))
        obj["blur_handle"] = f"{shape['handle']:#010x}"
        coll.objects.link(obj)
        obj.parent = parent
        obj.matrix_parent_inverse.identity()
        obj.matrix_basis = matrix
        if mesh is None:
            obj.empty_display_type = "PLAIN_AXES"
            obj.empty_display_size = 0.1
        else:
            obj.display_type = "SOLID"
            obj.show_wire = True
        return obj

    for o in objects:
        if o["type"] == 11:
            templates[o["handle"]] = o
    for o in objects:
        # a top-level object's space starts at its centre of mass; a body's shapes are placed
        # in it (checked: props then line up with their visible geometry to the millimetre)
        m = _placement(o["rotation"], [a + b for a, b in zip(o["position"], o["centre"])])
        if o["type"] == 10:
            src = templates.get(o["instance_of"])
            if src is None:
                continue
            o = dict(src, handle=o["handle"], rotation=o["rotation"], position=o["position"])
        if o["type"] == 7:
            body = add(o, m, root)
            for child in o["shapes"]:
                add(child, _placement(child["rotation"], child["position"]), body)
        else:
            add(o, m, root)
    return coll, []


class Imported:
    """What import_model made: notes for the user and the textures it loaded."""

    def __init__(self):
        self.notes, self.textures = [], []


def import_model(context, path, all_lods=False, shadows=True, collisions=True):
    with open(path, "rb") as fh:
        data = fh.read()
    sd = SceneData(data)
    if not sd.parts:
        raise blurmodel.ModelError("no drawable parts in this file")
    elements = blurmodel.read_elements(data, chunks.parse(data))
    model = Imported()
    model_name = os.path.splitext(os.path.basename(path))[0]

    scene_coll = context.scene.collection
    coll = bpy.data.collections.new(model_name)
    scene_coll.children.link(coll)

    root = bpy.data.objects.new(model_name, None)
    root.empty_display_type = "ARROWS"
    root["blur_model"] = path
    coll.objects.link(root)

    # Element empties, in hierarchy order (parents first in the table)
    empties = []
    for i, e in enumerate(elements):
        obj = bpy.data.objects.new(e.name or f"element {i}", None)
        obj.empty_display_type = "PLAIN_AXES"
        obj.empty_display_size = 0.1
        obj["blur_element"] = i
        obj["blur_tag"] = f"{e.tag:#010x}"  # 0xC00000nn: custom properties are 32-bit signed
        coll.objects.link(obj)
        empties.append(obj)
    # Element placements are absolute: each empty's local matrix is its placement
    # relative to its parent's.
    for i, e in enumerate(elements):
        obj = empties[i]
        has_parent = 0 <= e.parent < len(empties) and e.parent != i
        obj.parent = empties[e.parent] if has_parent else root
        world = element_matrix(e)
        obj.matrix_basis = (element_matrix(elements[e.parent]).inverted_safe() @ world) if has_parent else world
        # the placement in the file (relative to the root): the exporter measures meshes against
        # it, so moving an element's empty moves that part's vertices
        obj["blur_matrix"] = [x for row in world for x in row]

    stored = textures.stored(sd.scene)
    images = load_textures(stored, path, os.path.join(tempfile.gettempdir(), "blur_model_tools"))
    model.textures = stored
    mats = part_materials(sd, images, model_name)

    lod_count = max((len(p.lods) for p in sd.parts), default=1)
    lod_colls = {0: coll}
    if all_lods:
        for lod in range(1, lod_count):
            c = bpy.data.collections.new(f"{model_name} LOD{lod}")
            coll.children.link(c)
            lod_colls[lod] = c
    shadow_of = {p.key: parts.is_shadow(sd.layout(p)) for p in sd.parts}
    shadow_coll = None
    if shadows and any(shadow_of.values()):
        shadow_coll = bpy.data.collections.new(f"{model_name} Shadow")
        coll.children.link(shadow_coll)

    # Parts grouped by element, detail level and shadow-ness
    buckets = {}
    for p in sd.parts:
        shadow = shadow_of[p.key]
        if shadow and shadow_coll is None:
            continue
        for lod in (range(len(p.lods)) if all_lods else [0]):
            if lod < len(p.lods):
                buckets.setdefault((p.element, lod, shadow), []).append((p, lod))

    made = 0
    for (element, lod, shadow), items in sorted(buckets.items(), key=lambda kv: (kv[0][2], kv[0][1], kv[0][0])):
        has_element = 0 <= element < len(elements)
        base = elements[element].name if has_element and elements[element].name else f"part {element}"
        name = base + (" shadow" if shadow else "") + (f" LOD{lod}" if lod else "")
        mesh, keys = build_mesh(sd, name, items, {} if shadow else mats)
        if mesh is None:
            continue
        obj = bpy.data.objects.new(name, mesh)
        obj["blur_lod"] = lod
        obj["blur_shadow"] = shadow
        obj["blur_element"] = element if has_element else -1
        obj["blur_parts"] = ";".join(keys)
        (shadow_coll if shadow else lod_colls[lod]).objects.link(obj)
        obj.parent = empties[element] if has_element else root
        obj.matrix_parent_inverse.identity()
        if shadow:
            obj.display_type = "WIRE"
        made += 1
    if shadow_coll is not None:
        _exclude(context, shadow_coll)
    for lod, c in lod_colls.items():
        if lod:
            _exclude(context, c)
    if collisions:
        coll_coll, notes = import_collision(data, elements, model_name, coll, root)
        model.notes.extend(notes)
        if coll_coll is not None:
            _exclude(context, coll_coll)
    return model, made


def _exclude(context, coll):
    """Hides a collection in the view layer (it stays in the file)."""
    def find(layer_coll):
        if layer_coll.collection == coll:
            return layer_coll
        for child in layer_coll.children:
            found = find(child)
            if found:
                return found
        return None
    lc = find(context.view_layer.layer_collection)
    if lc is not None:
        lc.exclude = True
