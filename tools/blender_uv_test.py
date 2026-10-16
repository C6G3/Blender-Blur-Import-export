"""Checks the "second pair" UV maps (the 3rd and 4th numbers of a texture coordinate set):
veh_Light's "on" picture ("UV On / Dents") and smashed-and-on picture ("UV Smashed On").

    blender -b --factory-startup --python tools/blender_uv_test.py -- <car.model> <out folder>

Use a car with lights, e.g. dodge_viperacr_stock.model.
1. A light mesh gets both maps, holding the file's values.
2. Untouched: the export is the original byte for byte.
3. Only the "on" map of e_ReverseLight_Left moved: only those numbers change in the file.
4. The map deleted: the file's values are kept.
"""

import importlib.util
import os
import sys

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from blur import chunks, parts, scene  # noqa: E402

failed = []
ON, SMASHED_ON = "UV On / Dents", "UV Smashed On"
LIGHT = "e_reverselight_left"


def load_addon():
    spec = importlib.util.spec_from_file_location("blur_model_tools", os.path.join(REPO, "__init__.py"),
                                                  submodule_search_locations=[REPO])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["blur_model_tools"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    return mod


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failed.append(label)


def clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)


def read_scene(path):
    data = open(path, "rb").read()
    p = chunks.find_path(chunks.parse(data), "Scene")[-1]
    return scene.read(data, p.payload_offset, p.offset + p.size)


def export(mod, path, out):
    root = next(o for o in bpy.data.objects if "blur_model" in o)
    summary, _notes = mod.exporter.export_model(bpy.context, root, path, out)
    print("  ", summary)


def light_mesh():
    return next(o for o in bpy.data.objects
                if o.type == "MESH" and "blur_parts" in o and o.name.lower().startswith(LIGHT)
                and int(o.get("blur_lod", 0)) == 0)


def texcoords(s, key):
    """(TEXCOORD0, TEXCOORD1) of a part's vertices, up to four numbers each (none if absent)."""
    p = next(p for p in parts.parts(s) if p.key == key)
    vb = parts.vertex_buffer(s, p.vb)
    rows = parts.rows(vb)[p.base:p.base + p.span]
    els = parts.layout(vb)
    out = []
    for i in (0, 1):
        e = parts.find(els, parts.TEXCOORD, i)
        out.append(parts.decode(rows, e, 4) if e is not None else np.zeros((len(rows), 0), np.float32))
    return tuple(out)


def map_values(obj, name):
    layer = obj.data.uv_layers[name]
    uv = np.empty(len(layer.data) * 2, np.float32)
    layer.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    uv[:, 1] = 1.0 - uv[:, 1]
    return uv


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    path, out_dir = args[0], args[1]
    os.makedirs(out_dir, exist_ok=True)
    clear()
    mod = load_addon()
    original = read_scene(path)

    # 1. the maps, with the file's values
    bpy.ops.import_scene.blur_model(filepath=path)
    obj = light_mesh()
    names = [l.name for l in obj.data.uv_layers]
    print("   maps on", obj.name, names)
    check("light mesh has 'UV On / Dents' and 'UV Smashed On'", ON in names and SMASHED_ON in names)
    key = obj["blur_parts"].split(";")[0]   # part keys in slot order
    tc0, tc1 = texcoords(original, key)
    on = map_values(obj, ON)
    check("'UV On / Dents' holds the file's on positions",
          np.allclose([on[:, 0].min(), on[:, 0].max()], [tc0[:, 2].min(), tc0[:, 2].max()], atol=1e-4))
    smashed = map_values(obj, SMASHED_ON)
    check("'UV Smashed On' holds the file's smashed-on positions",
          np.allclose([smashed[:, 0].min(), smashed[:, 0].max()], [tc1[:, 2].min(), tc1[:, 2].max()], atol=1e-4))

    # 2. untouched
    out = os.path.join(out_dir, "uv_untouched.model")
    export(mod, path, out)
    check("untouched export is the original byte for byte", open(out, "rb").read() == open(path, "rb").read())

    # 3. the on picture moved right by 0.01
    layer = obj.data.uv_layers[ON]
    uv = np.empty(len(layer.data) * 2, np.float32)
    layer.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    uv[:, 0] += 0.01
    layer.data.foreach_set("uv", uv.ravel())
    out = os.path.join(out_dir, "uv_on_moved.model")
    export(mod, path, out)
    moved = read_scene(out)
    new0, new1 = texcoords(moved, key)
    check("same vertex count", len(new0) == len(tc0))
    if len(new0) == len(tc0):
        check("on positions moved by 0.01", np.allclose(np.sort(new0[:, 2]) - np.sort(tc0[:, 2]), 0.01, atol=1e-3))
        check("off positions unchanged", np.allclose(np.sort(new0[:, 0]), np.sort(tc0[:, 0])))
        check("smashed positions unchanged", np.allclose(np.sort(new1, axis=0), np.sort(tc1, axis=0)))
    others = [p.key for p in parts.parts(original) if p.key != key and p.vb is not None]
    same = all(np.array_equal(*[np.concatenate(texcoords(s, k), axis=1) for s in (original, moved)])
               for k in others if len(texcoords(moved, k)[0]) == len(texcoords(original, k)[0]))
    check("other parts' texture coordinates unchanged", same)

    # 4. the map deleted: the file's values stay
    clear()
    bpy.ops.import_scene.blur_model(filepath=path)
    obj = light_mesh()
    obj.data.uv_layers.remove(obj.data.uv_layers[ON])
    out = os.path.join(out_dir, "uv_on_deleted.model")
    export(mod, path, out)
    check("map deleted: export is the original byte for byte", open(out, "rb").read() == open(path, "rb").read())

    print("FAILED:", ", ".join(failed) if failed else "none")


main()
