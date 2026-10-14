"""Imports a .model in a background Blender and renders a picture of it.

    blender -b --factory-startup --python tools/blender_test.py -- <file.model> <out.png> [all_lods] [yaw]

Loads the add-on from this repository (no install needed), imports the model,
prints what was made and renders it with Workbench (textures shown) to <out.png>.
"""

import importlib.util
import math
import os
import sys

import bpy
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_addon():
    spec = importlib.util.spec_from_file_location("blur_model_tools", os.path.join(REPO, "__init__.py"),
                                                  submodule_search_locations=[REPO])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["blur_model_tools"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    return mod


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    path, out = args[0], args[1]
    all_lods = len(args) > 2 and args[2] == "1"
    yaw = float(args[3]) if len(args) > 3 else 35.0
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    load_addon()
    res = bpy.ops.import_scene.blur_model(filepath=path, all_lods=all_lods)
    print("RESULT", res)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    print("OBJECTS", len(bpy.data.objects), "MESHES", len(meshes), "TRIS", tris, "MATERIALS", len(bpy.data.materials),
          "IMAGES", len([i for i in bpy.data.images if i.packed_file]))
    for img in bpy.data.images:
        print("  IMAGE", img.name, tuple(img.size), img.get("blur_format"))

    # Camera framing everything visible
    bpy.context.view_layer.update()
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    centre, size = (lo + hi) / 2, max((hi - lo).length, 0.01)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    bpy.context.scene.collection.objects.link(cam)
    a = math.radians(yaw)
    cam.location = centre + Vector((math.sin(a) * size, -math.cos(a) * size, size * 0.45))
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 40
    scene = bpy.context.scene
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "TEXTURE"
    scene.display.shading.light = "STUDIO"
    scene.render.resolution_x, scene.render.resolution_y = 1000, 700
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("RENDERED", out)


main()
