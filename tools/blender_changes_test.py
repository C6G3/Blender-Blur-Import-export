"""Makes the kinds of changes people make in Blender to an imported car, exports, and checks
every one of them arrives (nothing falls back to the original).

    blender -b --factory-startup --python tools/blender_changes_test.py -- <car.model> <out folder>

1. Untouched: byte for byte the original.
2. A deleted mesh object: its parts stop being drawn.
3. A mesh put under another element's empty: its parts move to that element.
4. Two parts sharing material values, one given a different material: each keeps its own.
5. Collision: a hull scaled, a hull deleted, a body moved.
6. Detail levels imported, one level's mesh deleted: only that level goes.
The result must read back and import again.
"""

import importlib.util
import os
import sys

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from blur import chunks, collision, parts, scene  # noqa: E402

failed = []


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


def read_collision(path):
    data = open(path, "rb").read()
    c = chunks.find_path(chunks.parse(data), "Coll")[-1]
    return collision.read(data, c.payload_offset, c.offset + c.size)


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failed.append(label)


def clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)


def export(mod, path, out):
    root = next(o for o in bpy.data.objects if "blur_model" in o)
    summary, notes = mod.exporter.export_model(bpy.context, root, path, out)
    print("  ", summary)
    for n in notes:
        print("   note:", n)
    return root


def element_empty(name):
    return next(o for o in bpy.data.objects
                if o.type == "EMPTY" and o.name.lower() == name and "blur_collision" not in o)


def mesh_of(name):
    return next(o for o in bpy.data.objects
                if o.type == "MESH" and "blur_parts" in o and o.name.lower().startswith(name)
                and not o.get("blur_shadow") and int(o.get("blur_lod", 0)) == 0)


def drawn(s, key, level=0):
    p = next(p for p in parts.parts(s) if p.key == key)
    return level < len(p.lods) and p.lods[level][1] > 0


def gaps(s):
    """Index buffer stretches no draw covers, or covered twice (the game's own files have none;
    26Viewer can't read a buffer with one)."""
    by_ib = {}
    for p in parts.parts(s):
        for start, count, _lo, _n in p.lods:
            if count:
                by_ib.setdefault(p.ib, []).append((start, count))
    bad = 0
    for ref, ranges in by_ib.items():
        at = 0
        for start, count in sorted(ranges):
            bad += start != at
            at = max(at, start + count)
        bad += at != parts.index_buffer(s, ref)["count"]
    return bad


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    path, out_dir = args[0], args[1]
    os.makedirs(out_dir, exist_ok=True)
    clear()
    mod = load_addon()
    original = read_scene(path)

    # 1. untouched
    bpy.ops.import_scene.blur_model(filepath=path, collisions=True)
    out = os.path.join(out_dir, "untouched.model")
    export(mod, path, out)
    check("untouched export is the original byte for byte", open(out, "rb").read() == open(path, "rb").read())

    # 2-5 on one import
    bonnet = mesh_of("e_bonnet")
    bonnet_element = int(bonnet["blur_element"])
    bpy.data.objects.remove(bonnet)

    mirror = mesh_of("e_mirror_left")
    mirror_keys = str(mirror["blur_parts"]).split(";")
    door = element_empty("e_door_right")
    world = mirror.matrix_world.copy()
    mirror.parent = door
    mirror.matrix_world = world

    sd = mod.importer.SceneData(open(path, "rb").read())
    by_key = {p.key: p for p in sd.parts}
    shared = {}
    for obj in bpy.data.objects:
        if obj.type == "MESH" and "blur_parts" in obj and not obj.get("blur_shadow") and obj is not mirror:
            for slot, key in enumerate(str(obj["blur_parts"]).split(";")):
                p = by_key[key]
                if obj.material_slots[slot].material is not None:
                    shared.setdefault((id(p.rl), p.values), []).append((obj, slot, key))
    pair = next(v for v in shared.values() if len(v) >= 2)
    (obj_a, slot_a, key_a), (obj_b, slot_b, key_b) = pair[0], pair[1]
    mat = obj_b.material_slots[slot_b].material.copy()
    node = mod.materials.group_node(mat)
    number = next(i for i in node.inputs if i.type == "VALUE" and not i.is_linked)
    number.default_value = number.default_value + 0.25
    obj_b.material_slots[slot_b].link = "OBJECT"
    obj_b.material_slots[slot_b].material = mat
    print("   shared values:", key_a, key_b, "socket", number.name)

    hulls = [o for o in bpy.data.objects if o.get("blur_collision") == "hull"]
    by_body = {}
    for h in hulls:
        by_body.setdefault(h.parent.name, []).append(h)
    two = next(v for v in by_body.values() if len(v) >= 2)
    scaled, deleted = two[0], two[1]
    scaled_id, deleted_id = str(scaled["blur_shape"]), str(deleted["blur_shape"])
    scaled.scale = (1.5, 1.5, 1.5)
    bpy.data.objects.remove(deleted)
    body = next(o for o in bpy.data.objects if o.get("blur_collision") == "body" and o.name not in by_body)
    body_id = str(body["blur_shape"])
    body.location.z += 0.5

    out = os.path.join(out_dir, "changes.model")
    export(mod, path, out)
    s = read_scene(out)
    # (new parts renumber the parts after them: look by element)
    check("deleted bonnet mesh: nothing drawn on its element",
          not any(p.element == bonnet_element and p.lods[0][1] and not parts.is_shadow(parts.layout(
              parts.vertex_buffer(s, p.vb))) for p in parts.parts(s) if p.vb))
    check("other parts still drawn", sum(drawn(s, p.key) for p in parts.parts(s)) > 0)
    check("index buffers have no gaps (removed parts leave the buffers)", gaps(s) == 0)
    mirror_element = int(mirror["blur_element"])
    check("mirror moved: its old parts aren't drawn", all(not drawn(s, k) for k in mirror_keys))
    on_door = [p for p in parts.parts(s) if p.element == int(door["blur_element"]) and p.lods[0][1]]
    was_on_door = [p for p in parts.parts(original) if p.element == int(door["blur_element"]) and p.lods[0][1]]
    check(f"mirror moved: new parts on e_door_right ({len(was_on_door)} -> {len(on_door)})",
          len(on_door) == len(was_on_door) + len(mirror_keys))
    check("mirror moved: nothing left on its old element",
          not any(p.element == mirror_element and p.lods[0][1] for p in parts.parts(s)))
    pa = next(p for p in parts.parts(s) if p.key == key_a)
    pb = next(p for p in parts.parts(s) if p.key == key_b)
    check("shared material values split", pa.values != pb.values)
    table = pa.rl["values"] if "values" in pa.rl else pa.rl["materials"]["values"]
    check("the unchanged part keeps the original values",
          table["sets"][pa.values]["values"] == (lambda o: (o.rl["values"] if "values" in o.rl else
                                                            o.rl["materials"]["values"])["sets"][o.values]["values"])(
              by_key[key_a]))
    check("the changed part has new values",
          table["sets"][pb.values]["values"] != table["sets"][pa.values]["values"])

    cold, cnew = read_collision(path), read_collision(out)
    i, j = map(int, scaled_id.split("."))
    k = int(deleted_id.split(".")[1])
    old_body, new_body = cold[i], cnew[i]
    check(f"collision: hull deleted ({len(old_body['shapes'])} -> {len(new_body['shapes'])} shapes)",
          len(new_body["shapes"]) == len(old_body["shapes"]) - 1)
    new_j = j - (1 if k < j else 0)
    a = np.array(old_body["shapes"][j]["vertices"])
    b = np.array(new_body["shapes"][new_j]["vertices"])
    check(f"collision: hull scaled ({np.ptp(a, 0).round(3)} -> {np.ptp(b, 0).round(3)})",
          np.allclose(np.ptp(b, 0), np.ptp(a, 0) * 1.5, atol=1e-3))
    bi = int(body_id)
    check(f"collision: body moved up ({cold[bi]['position'][1]:.3f} -> {cnew[bi]['position'][1]:.3f})",
          abs(cnew[bi]["position"][1] - cold[bi]["position"][1] - 0.5) < 1e-4)
    check("collision: same number of objects", len(cnew) == len(cold))

    clear()
    print("REIMPORT", bpy.ops.import_scene.blur_model(filepath=out, collisions=True))
    check("re-imported: no bonnet mesh", not any(o.type == "MESH" and o.name.lower().startswith("e_bonnet")
                                                  and not o.get("blur_shadow") for o in bpy.data.objects))

    # 6. detail levels
    clear()
    bpy.ops.import_scene.blur_model(filepath=path, all_lods=True, collisions=False)
    lod1 = next((o for o in bpy.data.objects if o.type == "MESH" and int(o.get("blur_lod", 0)) == 1
                 and not o.get("blur_shadow") and o.name.lower().startswith("e_exterior")), None)
    if lod1 is None:
        print("   (no LOD1 exterior mesh; level test skipped)")
    else:
        keys = str(lod1["blur_parts"]).split(";")
        bpy.data.objects.remove(lod1)
        out = os.path.join(out_dir, "lod1.model")
        export(mod, path, out)
        s = read_scene(out)
        check("deleted LOD1 mesh: level 1 not drawn", all(not drawn(s, k, 1) for k in keys))
        check("deleted LOD1 mesh: level 0 unchanged", all(drawn(s, k, 0) == drawn(original, k, 0) for k in keys))
    print("FAILED:", failed if failed else "none")


main()
