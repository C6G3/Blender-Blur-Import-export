"""Builds Blender objects from a Blur model (blur.model.Model).

Layout in the scene:

    <model> (empty, the file)                     collection "<model>"
      e_exterior (empty, a MdlDat element)
        e_exterior (mesh: the element's parts at detail level 0, one material slot each)
        e_door_left (empty) > e_door_left (mesh) ...
    collections "<model> LOD1".. hold lower detail levels, "<model> Shadow" the
    shadow hulls (hidden)

Coordinates: Blur is Direct3D (left-handed, x right, y up, z forward); Blender
is right-handed z-up, so (x, y, z) -> (x, z, y). Swapping two axes also turns
the triangles' clockwise front faces into Blender's counter-clockwise ones.
Mesh vertices stay in their element's own space; the element empties carry the
placement (MdlDat rotation and position), so parts move like in the game.
"""

import os
import tempfile

import bpy
import numpy as np
from mathutils import Matrix

from . import materials
from .blur import dds
from .blur import model as blurmodel


# ---- vertex data ---------------------------------------------------------------------------

def _column(model, vb, offset, dtype, components):
    """One element of every vertex in `vb` as an (n, components) array."""
    raw = np.frombuffer(model.data, dtype=np.uint8, count=vb.size, offset=vb.start).reshape(vb.count, vb.stride)
    width = np.dtype(dtype).itemsize * components
    return raw[:, offset:offset + width].copy().view(dtype).reshape(vb.count, components)


def positions(model, vb):
    if vb.position_bytes == 8:
        p = _column(model, vb, 0, np.float16, 4)[:, :3].astype(np.float32)
    else:
        p = _column(model, vb, 0, np.float32, 3)
    return np.nan_to_num(p, nan=0.0, posinf=0.0, neginf=0.0)


def _ubyte4n(model, vb, offset):
    return _column(model, vb, offset, np.uint8, 4).astype(np.float32) / 127.5 - 1.0


def normals(model, vb):
    e = vb.element(blurmodel.NORMAL, 0, (blurmodel.UBYTE4N,))
    return None if e is None else _ubyte4n(model, vb, e.offset)[:, :3]


def uvs(model, vb, index):
    e = vb.element(blurmodel.TEXCOORD, index, (blurmodel.HALF2, blurmodel.HALF4, blurmodel.FLOAT3,
                                              blurmodel.FLOAT4))
    if e is None and index == 0 and not vb.elements and len(vb.offsets) > 2:
        return None
    if e is None:
        return None
    if e.type in (blurmodel.HALF2, blurmodel.HALF4):
        uv = _column(model, vb, e.offset, np.float16, 2).astype(np.float32)
    else:
        uv = _column(model, vb, e.offset, np.float32, 2)
    return np.nan_to_num(uv)


def colors(model, vb):
    """Vertex colour (usage 10 = COLOR in Blur's numbering: 9 or 10, four bytes) or None."""
    for usage in (10, 9):
        e = vb.element(usage, 0, (blurmodel.UBYTE4N, blurmodel.UBYTE4))
        if e is not None:
            return _column(model, vb, e.offset, np.uint8, 4).astype(np.float32) / 255.0
    return None


SWAP = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def element_matrix(e):
    r, t = e.rotation, e.position
    # row vectors p' = p R + t  ->  column form [[R^T, t], [0, 1]], then into Blender axes
    m = Matrix(((r[0], r[3], r[6], t[0]), (r[1], r[4], r[7], t[1]), (r[2], r[5], r[8], t[2]), (0, 0, 0, 1)))
    return SWAP @ m @ SWAP


# ---- textures ------------------------------------------------------------------------------

def load_textures(model, name, folder):
    """Every stored texture as a Blender image (written as .dds into `folder` and packed)."""
    images = []
    os.makedirs(folder, exist_ok=True)
    for i, t in enumerate(model.textures):
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in t.name) or f"texture_{i + 1}"
        path = os.path.join(folder, f"{safe}.dds")
        if os.path.exists(path):
            path = os.path.join(folder, f"{safe}_{i + 1}.dds")
        with open(path, "wb") as fh:
            fh.write(dds.write(t.format, t.width, t.height, t.mip_count, t.pixels(model.data)))
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
        images.append(img)
    return images


# ---- materials -----------------------------------------------------------------------------

def make_materials(model, images, model_name):
    """One Blender material per distinct (effect, values) pair; returns group -> material."""
    by_key, out = {}, {}
    for g in model.groups:
        effect = model.effects[g.material] if g.material < len(model.effects) else "default_NB.fx"
        vs = model.value_sets[g.values] if 0 <= g.values < len(model.value_sets) else None
        textures, values = {}, {}
        if vs is not None:
            for input_name, index in vs.textures:
                t = model.texture_order[index] if 0 <= index < len(model.texture_order) else -1
                textures[input_name] = images[t] if 0 <= t < len(images) else None
            for input_name, numbers in vs.constants:
                values[input_name] = numbers
            for input_name, numbers in vs.integers:
                values[input_name] = numbers
        key = (effect, tuple(sorted((k, v.name if v else "") for k, v in textures.items())),
               tuple(sorted((k, tuple(v)) for k, v in values.items())))
        if key not in by_key:
            base = effect.rsplit(".", 1)[0]
            color = next((img.name for k, img in textures.items() if img and materials.texture_role(k) == "color"),
                         None)
            mat = materials.new_material(effect, f"{model_name} {base}" + (f" {color}" if color else ""),
                                         textures, values)
            by_key[key] = mat
        out[id(g)] = by_key[key]
    return out


# ---- meshes --------------------------------------------------------------------------------

def build_mesh(model, name, parts, mats, cache):
    """A mesh of `parts` [(group, lod)], all in one element's space, one material slot each."""
    verts, norms, uv0, uv1, cols, faces, face_mat, slot_of = [], [], [], [], [], [], [], {}
    mesh = bpy.data.meshes.new(name)
    total = 0
    for g, lod in parts:
        tris = blurmodel.triangles(model, g, lod)
        if not tris:
            continue
        vb = model.vertex_buffers[g.vertex_buffer]
        if g.vertex_buffer not in cache:
            cache[g.vertex_buffer] = (positions(model, vb), normals(model, vb), uvs(model, vb, 0), uvs(model, vb, 1),
                                      colors(model, vb))
        pos, nrm, t0, t1, col = cache[g.vertex_buffer]
        tri = np.asarray(tris, dtype=np.int64)
        used, remap = np.unique(tri, return_inverse=True)
        verts.append(pos[used][:, [0, 2, 1]])
        norms.append(nrm[used][:, [0, 2, 1]] if nrm is not None else np.zeros((len(used), 3), np.float32))
        uv0.append(t0[used] if t0 is not None else np.zeros((len(used), 2), np.float32))
        uv1.append(t1[used] if t1 is not None else None)
        cols.append(col[used] if col is not None else None)
        faces.append(remap.reshape(-1, 3) + total)
        mat = mats.get(id(g))
        if mat not in slot_of:
            slot_of[mat] = len(slot_of)
            mesh.materials.append(mat)
        face_mat.append(np.full(len(tri), slot_of[mat], np.int32))
        total += len(used)
    if not faces:
        bpy.data.meshes.remove(mesh)
        return None
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
        if any(a is None for a in layer):
            if layer_name != "UVMap":
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
    return mesh


def import_model(context, path, all_lods=False, shadows=True):
    with open(path, "rb") as fh:
        data = fh.read()
    model = blurmodel.read(data)
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
    for i, e in enumerate(model.elements):
        obj = bpy.data.objects.new(e.name or f"element {i}", None)
        obj.empty_display_type = "PLAIN_AXES"
        obj.empty_display_size = 0.1
        obj["blur_element"] = i
        obj["blur_tag"] = f"{e.tag:#010x}"  # 0xC00000nn: custom properties are 32-bit signed
        coll.objects.link(obj)
        empties.append(obj)
    # Element placements are absolute: each empty's local matrix is its placement
    # relative to its parent's.
    for i, e in enumerate(model.elements):
        obj = empties[i]
        has_parent = 0 <= e.parent < len(empties) and e.parent != i
        obj.parent = empties[e.parent] if has_parent else root
        world = element_matrix(e)
        obj.matrix_basis = (element_matrix(model.elements[e.parent]).inverted_safe() @ world) if has_parent else world

    images = load_textures(model, model_name, os.path.join(tempfile.gettempdir(), "blur_model_tools"))
    mats = make_materials(model, images, model_name)

    lod_count = max((len(g.lods) for g in model.groups), default=1)
    lod_colls = {0: coll}
    if all_lods:
        for lod in range(1, lod_count):
            c = bpy.data.collections.new(f"{model_name} LOD{lod}")
            coll.children.link(c)
            lod_colls[lod] = c
    shadow_coll = None
    if shadows and any(g.shadow for g in model.groups):
        shadow_coll = bpy.data.collections.new(f"{model_name} Shadow")
        coll.children.link(shadow_coll)

    # Parts grouped by element, detail level and shadow-ness
    buckets = {}
    for g in model.groups:
        if g.shadow and shadow_coll is None:
            continue
        for lod in (range(len(g.lods)) if all_lods else [0]):
            if lod < len(g.lods):
                buckets.setdefault((g.element, lod, g.shadow), []).append((g, lod))

    cache, made = {}, 0
    for (element, lod, shadow), parts in sorted(buckets.items(), key=lambda kv: (kv[0][2], kv[0][1], kv[0][0])):
        has_element = 0 <= element < len(model.elements)
        base = model.elements[element].name if has_element and model.elements[element].name else f"part {element}"
        name = base + (" shadow" if shadow else "") + (f" LOD{lod}" if lod else "")
        mesh = build_mesh(model, name, parts, {} if shadow else mats, cache)
        if mesh is None:
            continue
        obj = bpy.data.objects.new(name, mesh)
        obj["blur_lod"] = lod
        obj["blur_shadow"] = shadow
        obj["blur_element"] = element if has_element else -1
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
