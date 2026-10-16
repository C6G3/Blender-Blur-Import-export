# Blender Blur Import/Export

A Blender 5 add-on for **Blur** (Bizarre Creations, 2010) `.model` files: cars, characters,
props and effects, with their part hierarchy, Blur materials, the textures stored in them
and their collision. Import, edit, add parts, export back into the game.
The format knowledge comes from [26Viewer](https://github.com/C6G3/26Viewer)
(`docs/formats/blur.md`).

## What it does

- **File ▸ Import ▸ Blur Model (.model)**
  - Every part, placed by the model's own hierarchy (`e_exterior` › `e_door_left` ›
    `e_mirror_left` …) as empties you can move like the game does.
  - Normals, UVs (both sets) and vertex colours.
  - **Extra UV maps** where the model uses them: a texture coordinate set can hold a
    second position, and its meaning depends on the effect.
    - **UV On / Dents** — lights (`veh_Light`): where the *on* picture is (`UVMap` is the
      *off* one); paint and glass: where the dent and scratch maps go.
    - **UV Smashed On** — lights: the smashed-and-on picture (`UVMap.001` is smashed-off).

    A light's texture holds each light three times — off, on (glowing) and smashed — and
    the game cross-fades from the off to the on picture when the light is switched on.
    Move a light's *UV On / Dents* together with its `UVMap`, or the glow appears in the
    wrong place. Deleting one of these maps keeps the model's own values.
  - The textures stored in the model, packed into the .blend with their original
    compression (DXT1/3/5…), named like in the game.
  - One material per Blur material, using the game's effect (see below).
  - Options: all detail levels (each in its own hidden collection), shadow hulls,
    **collision** (hidden *Collision* collection: meshes, hulls, boxes, spheres,
    cylinders, capsules; each triangle's surface — Tarmac, Metal, Glass… — is its
    material).
- **Blur materials.** In *Material Properties ▸ Blur Material*,
  click **Choose Blur Effect…** and pick one of the game's 106 effects (`veh_Paint_a`,
  `veh_Glass_c_h`, `veh_Default_b_f`, `default_NL_NV`, `MeshEffect`…) — every one is
  explained in **[BLUR_MATERIALS.md](BLUR_MATERIALS.md)**: what the name letters mean,
  every input, where the game uses it. The material gets a **Blur Shader** node group
  with one socket per input the game gives that effect, plus an Image Texture node for
  each texture slot. Pick images in the panel (the folder button opens one from disk);
  the panel also shows which textures the game normally uses in each slot and the
  effect's parameters (`g_vMtlParameters`…) with the game's usual values. Paint has no
  colour texture (Blur paints the car itself): its viewport colour is only a preview.
- **File ▸ Export ▸ Blur Model (.model)** — write the imported model back with your edits.
  - No need to select everything: the model of the active object is exported (with only
    one model in the scene, nothing needs selecting). Export to a new file (the original
    is the starting point and is never overwritten; by default `<name>_edited.model` next
    to it). Put it back into the game with 26Viewer (Edit Mode ▸ Replace). The status bar
    shows how long the import or export took; an untouched export is byte for byte the
    original.
  - **What you see in Blender is what gets written.** Every material slot of an imported
    mesh is one part of the model; its faces become that part's new geometry: move, add
    or delete vertices and faces, re-UV, repaint vertex colours. Moving a part or its
    element's empty moves the part. **Deleting a mesh object** (or leaving a slot with no
    faces) removes its parts from the model. **Putting a mesh under another element's
    empty** (e.g. a mirror under `e_door_right`) moves its parts to that element, so they
    move with it in the game. Only parts you didn't import at all (detail levels or shadow
    hulls left out at import) stay as they were. Edits still in Edit Mode are included;
    hidden objects are still exported (delete what you want gone).
  - **Detail levels.** An imported `LOD1`–`LOD3` mesh is used for its level; without one,
    the edit of LOD0 is drawn at the lower levels too.
  - **Materials.** The numbers in the Blur Shader node and the images in its texture
    slots are written to the part. A slot can take any texture the model holds, or a
    new picture: a `.dds` with mipmaps is stored as it is; anything else (and a `.dds`
    without mipmaps — the game's textures always have them) is compressed to DXT1 (DXT5 if
    it has transparency) with mipmaps and added to the model. Parts that shared one set of
    material values get their own as soon as you give them different materials.
  - **New parts.** Faces in a material slot you add to an imported mesh, and any new
    mesh object you put under the model (parented to an element's empty, e.g.
    `e_exterior`, or to the model), become new parts on that element — one per Blur
    material. Switching a slot's material to another Blur effect moves those faces to a
    new part drawn with it. The effect must be one the model already uses (a new part
    copies such a part's settings); the export lists them when it isn't.
  - What Blender doesn't show (damage offsets on cars, bone weights on characters) is
    kept from the original vertex, or copied from the nearest one for new vertices.
    Unmoved vertices keep their exact normals until you *Clear Custom Split Normals*.
  - **Collision.** Convex hulls you edit, scale, move or delete, and collision bodies you
    move, are written back (a body keeps at least one shape). Models imported with an
    older version of the add-on need importing again for this.
  - Not yet: effects a model doesn't use, new elements (part names / hierarchy), moving
    elements themselves (their placement is baked into the vertices), collision meshes and
    boxes/spheres/capsules, new collision shapes.

**Cars and their wheels.** A car's `.model` has its own four tyres, brake discs and callipers
(each wheel its own copy, not shared), but the **rim** the game draws comes from a separate
model, `models/vehicles/wheels/<car>.model` (one rim, used for all four wheels; Blur.exe
loads it next to the car, `default.model` when a car has none). To change a car's rims, edit
that wheel model (it imports and exports like any other); the car's own `e_alloyRim_…`
parts are most likely not what you see in a race.

**Making a model "from scratch":** import a model of the same kind (a car for a car),
delete its meshes or empty their slots, model your own under its element empties
(`e_exterior`, `e_door_left`, `e_wheel_…` — the game moves those), give each mesh Blur
materials the model uses, export. The original's elements, collision and shadow are kept.

The preview inside the node group is an approximation (Principled BSDF with the colour
texture, normal map and alpha); the game's own shaders aren't reproduced.

## Install

1. Build the zip with Blender:
   `blender --command extension build --source-dir <this folder> --output-dir <folder>`,
   then in Blender: *Edit ▸ Preferences ▸ Get Extensions ▸ ⌄ ▸ Install from Disk…* and
   pick the zip.
2. Get `.model` files out of the game's archives with
   [26Viewer](https://github.com/C6G3/26Viewer) (select ▸ Extract).

Requires Blender 5.0 or newer.

## Roadmap

1. ✅ Import: geometry, hierarchy, materials, textures, detail levels, shadow hulls, collision.
2. ✅ Blur material presets (106 effects from every model in the game) and
   [BLUR_MATERIALS.md](BLUR_MATERIALS.md).
3. ✅ The scene stream (`Render/Scene`, an "ARCH" serialized object graph) read and
   written back byte for byte for all 1,744 models (`blur/scene.py`, field order from
   Blur.exe's loader).
4. ✅ Export of edited geometry for existing parts, every detail level, shadow hulls.
5. ✅ Export of material numbers and textures (any of the model's, or new pictures).
6. ✅ New parts and switching a part's effect (effects the model uses).
7. ✅ Every change in Blender written: deleted objects and slots, meshes moved to another
   element, per-part materials, collision hulls and bodies.
8. Effects a model doesn't use (new material entries, vertex formats), new elements,
   collision meshes and primitives, damage bones, skinning to `.skeleton` bones.

## Layout

| Path | What |
|---|---|
| `blur/` | The format code (plain Python + numpy, no Blender needed): chunk files (`chunks.py`), the scene stream (`scene.py`), parts, buffer rebuilding and new parts (`parts.py`), textures and DXT compression (`textures.py`), collision (`collision.py`), DDS (`dds.py`), the older pattern reader (`model.py`: element table, presets scan) |
| `importer.py`, `exporter.py`, `materials.py`, `__init__.py` | The Blender side |
| `presets/effects.json` | Every Blur effect's passes, inputs, usual values, textures and where it's used |
| `BLUR_MATERIALS.md` | Every effect explained (`python tools/make_materials_doc.py`) |
| `tools/scan_effects.py` | Rebuilds `effects.json` from the game (`python tools/scan_effects.py F:/Games/BLUR`) |
| `tools/check_scene.py` | Reads and rewrites every model's scene stream; must come out byte for byte |
| `tools/check_parts.py` | Rebuilds every model's buffers from its own parts; must draw the same |
| `tools/check_all_models.py` | Reads every model with the older reader |
| `tools/blender_test.py` | Imports a model in a background Blender and renders a picture |
| `tools/blender_export_test.py` | Imports, exports unchanged and with a part scaled, and compares |
| `tools/blender_edit_test.py` | Moves a part, edits in Edit Mode, changes materials and textures; checks they arrive |
| `tools/blender_newparts_test.py` | Adds a new object, a new slot and an effect switch; checks they arrive |
| `tools/blender_changes_test.py` | Deletes meshes and a detail level, moves a mesh to another element, splits shared materials, edits collision; checks every change arrives |

## License

MIT — see [LICENSE](LICENSE).
