"""Adds parts to an imported car in a background Blender, exports, and checks they arrive.

    blender -b --factory-startup --python tools/blender_newparts_test.py -- <car.model> <out folder>

1. A new object (a cube with a new Blur material and a new picture) under an element.
2. A material slot added to an imported mesh, with some of its faces moved into it.
3. An existing part's slot switched to another effect the model has (a new part takes
   its faces, the old one stops being drawn).
4. An effect the model doesn't have: must be reported and skipped.
The result must read back, hold the new parts with the right effects and import again.
"""

import importlib.util
import os
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


def effect_of(s, p):
    table = p.rl["values"] if "values" in p.rl else p.rl["materials"]["values"]
    return p.rl["materials"]["types"][table["sets"][p.values]["type"]]["effect"]


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    path, out_dir = args[0], args[1]
    os.makedirs(out_dir, exist_ok=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    mod = load_addon()
    bpy.ops.import_scene.blur_model(filepath=path)
    root = next(o for o in bpy.data.objects if "blur_model" in o)
    coll = root.users_collection[0]
    bpy.context.view_layer.objects.active = root

    # 1. a new cube under the exterior element, Default effect with a new picture
    exterior = next(o for o in bpy.data.objects if o.type == "EMPTY" and o.name.lower() == "e_exterior")
    me = bpy.data.meshes.new("my_spoiler")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.4)
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")
    cube = bpy.data.objects.new("my_spoiler", me)
    coll.objects.link(cube)
    cube.parent = exterior
    cube.location = (0, -2.0, 1.2)
    mat = mod.materials.new_material("veh_Default_b_c_f_h.fx", "my spoiler mat")
    pic = bpy.data.images.new("spoiler_carbon", 64, 64)
    pic.generated_color = (0.1, 0.1, 0.1, 1)
    mod.materials.assign_image(mat, "g_MeshTexture", pic)
    me.materials.append(mat)

    # 2. a new slot on the bonnet mesh: half its faces become glass
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and "blur_parts" in o and not o.get("blur_shadow")]
    bonnet = next(o for o in meshes if "bonnet" in o.name.lower())
    glass = next(m for m in bpy.data.materials if mod.materials.material_effect(m).lower().startswith("veh_glass"))
    bonnet.data.materials.append(glass)
    new_slot = len(bonnet.data.materials) - 1
    for poly in bonnet.data.polygons[: len(bonnet.data.polygons) // 2]:
        poly.material_index = new_slot

    # 3. switch a door's first slot to the Matt effect (tyres use it)
    door = next(o for o in meshes if "door_left" in o.name.lower())
    matt = next(m for m in bpy.data.materials if mod.materials.material_effect(m).lower().startswith("veh_matt"))
    switched_key = str(door["blur_parts"]).split(";")[0]
    door.material_slots[0].material = matt

    # 4. an effect the car doesn't use
    me2 = bpy.data.meshes.new("water_test")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.2)
    bm.to_mesh(me2)
    bm.free()
    w = bpy.data.objects.new("water_test", me2)
    coll.objects.link(w)
    w.parent = root
    me2.materials.append(mod.materials.new_material("Water_NL_NV.fx"))

    out = os.path.join(out_dir, "newparts.model")
    print("EXPORT", bpy.ops.export_scene.blur_model(filepath=out, source=path))

    a, b = read_scene(path), read_scene(out)
    pa = [p for p in parts.parts(a) if p.kind == "static"]
    pb = [p for p in parts.parts(b) if p.kind == "static"]
    # the spoiler, the bonnet's glass slot, the door slot moved to another effect
    check(f"three new parts ({len(pa)} -> {len(pb)})", len(pb) == len(pa) + 3)
    effects_b = [effect_of(b, p) for p in pb]
    check("a new veh_Default_b_c_f_h part exists",
          sum(e.lower() == "veh_default_b_c_f_h.fx" for e in effects_b) > sum(
              effect_of(a, p).lower() == "veh_default_b_c_f_h.fx" for p in pa))
    old_switched = next(p for p in parts.parts(a) if p.key == switched_key)
    still = [p for p in pb if p.record["w"][4] == old_switched.record["w"][4]
             and effect_of(b, p) == effect_of(a, old_switched) and p.lods[0][1]]
    check("the switched door part isn't drawn with its old effect any more", not any(
        p.lods[0][1] and p.lods[0][2] == old_switched.lods[0][2] and p.lods[0][1] == old_switched.lods[0][1]
        for p in still))
    rl = parts.render_lists(b)[0][1]
    six_sum = sum(x["w"][0] for x in rl["six"]["items"])
    check(f"buckets add up ({six_sum} == {len(rl['static']['items'])})", six_sum == len(rl["static"]["items"]))
    check("one box per part", len(rl["bounds_a"]["items"]) == len(rl["static"]["items"]))
    lod = rl["lod_a"]
    check("visibility rows have a bit per part", lod["b"] == (len(rl["static"]["items"]) + 7) // 8)
    check("the new picture is stored", any(t["name"] == "spoiler_carbon" for t in b["scene"]["keyed"]))

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    print("REIMPORT", bpy.ops.import_scene.blur_model(filepath=out))
    names = {n.image.name.split(".")[0] for m in bpy.data.materials if m.node_tree
             for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image}
    check("re-imported: the spoiler's picture is used", "spoiler_carbon" in names)
    ext = [o for o in bpy.data.objects if o.type == "MESH" and o.name.lower().startswith("e_exterior")]
    zs = [max((o.matrix_world @ v.co).z for v in o.data.vertices) for o in ext]
    print("  exterior mesh top", np.round(zs, 2))


main()
