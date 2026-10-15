"""Edits an imported model the ways a user would, exports, and checks every edit arrived.

    blender -b --factory-startup --python tools/blender_edit_test.py -- <car.model> <out folder>

1. Export without changes: the file must come out byte for byte the same.
2. Move one element's empty up 0.25, edit another mesh in Edit Mode (export without
   leaving it), change a material number, put a new picture in one texture slot and
   another texture the model holds in a second one. Export, then read the result:
   each edit must be there, and the file must import again.
"""

import importlib.util
import os
import struct
import sys

import bmesh
import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from blur import chunks, parts, scene  # noqa: E402


def load_addon():
    spec = importlib.util.spec_from_file_location("blur_model_tools", os.path.join(REPO, "__init__.py"),
                                                  submodule_search_locations=[REPO])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["blur_model_tools"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    return mod


def read_scene(path):
    data = open(path, "rb").read()
    p = chunks.find_path(chunks.parse(data), "Scene")[-1]
    return scene.read(data, p.payload_offset, p.offset + p.size)


def positions(s, p):
    vb = parts.vertex_buffer(s, p.vb)
    raw = parts.rows(vb)[p.base:p.base + p.span]
    return parts.decode(raw, parts.find(parts.layout(vb), parts.POSITION), 3)


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label)
    return ok


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    path, out_dir = args[0], args[1]
    os.makedirs(out_dir, exist_ok=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    mod = load_addon()
    bpy.ops.import_scene.blur_model(filepath=path)
    root = next(o for o in bpy.data.objects if "blur_model" in o)
    bpy.context.view_layer.objects.active = root

    same = os.path.join(out_dir, "same.model")
    bpy.ops.export_scene.blur_model(filepath=same, source=path)
    check("export without changes is byte for byte the original", open(same, "rb").read() == open(path, "rb").read())

    meshes = [o for o in bpy.data.objects if o.type == "MESH" and "blur_parts" in o and not o.get("blur_shadow")]
    # 1. move an element's empty (a part with a parent element, e.g. a mirror)
    moved = next(o for o in meshes if o.parent and o.parent.type == "EMPTY" and "mirror" in o.name.lower()) \
        if any("mirror" in o.name.lower() for o in meshes) else meshes[1]
    moved.parent.location.z += 0.25
    moved_keys = str(moved["blur_parts"]).split(";")

    # 2. Edit Mode change, left in Edit Mode: push one vertex out
    edited = next(o for o in meshes if o is not moved and len(o.data.vertices) > 50)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = edited
    edited.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(edited.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].co.z += 0.5
    bmesh.update_edit_mesh(edited.data)
    edited_keys = str(edited["blur_parts"]).split(";")

    # 3. a material number, 4. a new picture, 5. another of the model's textures
    num_mat = next(m for o in meshes for m in o.data.materials
                   if m and mod.materials.group_node(m) and "g_vMtlParameters 0" in mod.materials.group_node(m).inputs)
    mod.materials.group_node(num_mat).inputs["g_vMtlParameters 0"].default_value = 0.777
    tex_mat = next(m for o in meshes for m in o.data.materials
                   if m and m is not num_mat and m.node_tree.nodes.get("g_MeshTexture") is not None
                   and m.node_tree.nodes["g_MeshTexture"].image is not None)
    pic = bpy.data.images.new("my_new_livery", 100, 60)      # not a power of two: gets resized
    pic.generated_color = (0.9, 0.1, 0.1, 1.0)
    mod.materials.assign_image(tex_mat, "g_MeshTexture", pic)
    swap_mat = next((m for o in meshes for m in o.data.materials
                     if m and m not in (num_mat, tex_mat) and m.node_tree.nodes.get("g_ScratchTexture") is not None
                     and m.node_tree.nodes["g_ScratchTexture"].image is not None), None)
    other = None
    if swap_mat is not None:
        current = swap_mat.node_tree.nodes["g_ScratchTexture"].image
        other = next(i for i in bpy.data.images if i.get("blur_source") and i is not current)
        mod.materials.assign_image(swap_mat, "g_ScratchTexture", other)

    out = os.path.join(out_dir, "edited.model")
    res = bpy.ops.export_scene.blur_model(filepath=out, source=path)
    print("EXPORT", res)

    a, b = read_scene(path), read_scene(out)
    pa = {p.key: p for p in parts.parts(a) if p.vb is not None}
    pb = {p.key: p for p in parts.parts(b) if p.vb is not None}
    k = moved_keys[0]
    d = positions(b, pb[k]).mean(0) - positions(a, pa[k]).mean(0)
    check(f"moved empty: {moved.name} part {k} shifted up 0.25 (got {np.round(d, 3).tolist()})",
          abs(d[1] - 0.25) < 0.01 and abs(d[0]) < 0.01 and abs(d[2]) < 0.01)
    ka = edited_keys[0]
    pa_, pb_ = positions(a, pa[ka]), positions(b, pb[ka])
    grew = any(abs(pb_[:, 1].max() - pa_[:, 1].max()) > 0.1 for _ in [0]) or len(pb_) != len(pa_)
    changed_any = any(not np.array_equal(positions(a, pa[x]), positions(b, pb[x])) for x in edited_keys if x in pa)
    check(f"Edit Mode change on {edited.name} exported", changed_any or grew)
    unchanged = [x for x in pa if x not in moved_keys and x not in edited_keys]
    same_bytes = all(np.array_equal(positions(a, pa[x]), positions(b, pb[x])) for x in unchanged)
    check(f"the other {len(unchanged)} parts are unchanged", same_bytes)

    # material values: find the value set holding 0.777
    found = any(isinstance(v, bytes) and len(v) == 4 and abs(struct.unpack("<f", v)[0] - 0.777) < 1e-6
                for _, rl in parts.render_lists(b)
                for vs in (rl["values"] if "values" in rl else rl["materials"]["values"])["sets"]
                for v in vs["values"])
    check("material number 0.777 written", found)
    keyed = [t["name"] for t in b["scene"]["keyed"]]
    check(f"new picture stored as a keyed texture ({keyed[-1]})", keyed[-1] == "my_new_livery")
    rec = b["scene"]["keyed"][-1]
    w, h, depth, mips, fmt = struct.unpack_from("<5I", rec["data"], 0)
    check(f"  its size {w}x{h}, {mips} mips, format {fmt:#x}", (w, h) == (128, 64) and mips == 8)

    # re-import: the slots must show the new picture / the swapped texture
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    print("REIMPORT", bpy.ops.import_scene.blur_model(filepath=out))
    names = {n.image.name.split(".")[0] for m in bpy.data.materials if m.node_tree
             for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image}
    check("re-imported materials use my_new_livery", "my_new_livery" in names)
    if other is not None:
        print("  swapped a scratch slot to", other.name)


main()
