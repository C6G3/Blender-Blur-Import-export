# Blender Blur Import/Export

A Blender 5 add-on for **Blur** (Bizarre Creations, 2010) `.model` files: cars, characters,
props and effects, with their part hierarchy, Blur materials and the textures stored in them.
The format knowledge comes from [26Viewer](https://github.com/C6G3/26Viewer)
(`docs/formats/blur.md`).

## What it does

- **File ▸ Import ▸ Blur Model (.model)**
  - Every part, placed by the model's own hierarchy (`e_exterior` › `e_door_left` ›
    `e_mirror_left` …) as empties you can move like the game does.
  - Normals, UVs (both sets) and vertex colours.
  - The textures stored in the model, packed into the .blend with their original
    compression (DXT1/3/5…), named like in the game.
  - One material per Blur material, using the game's effect (see below).
  - Options: all detail levels (each in its own hidden collection), shadow hulls.
- **Blur materials (like Sollumz shaders).** In *Material Properties ▸ Blur Material*,
  click **Choose Blur Effect…** and pick one of the game's 106 effects (all explained in
  [BLUR_MATERIALS.md](BLUR_MATERIALS.md)) (`veh_Paint_a`,
  `veh_Glass_c_h`, `veh_Default_b_f`, `default_NL_NV`, `MeshEffect`…). The material gets a
  **Blur Shader** node group with one socket per input the game gives that effect, plus an
  Image Texture node for each texture slot. Pick images in the panel; the panel also shows
  which textures the game normally uses in each slot and the effect's parameters
  (`g_vMtlParameters`…) with the game's usual values. Switching to another effect keeps the
  images already plugged in.
- **File ▸ Export ▸ Blur Model (.model)** — edit an imported model and write it back.
  - Select any object of the imported model, export to a new file (the original is
    the starting point and is never overwritten; by default `<name>_edited.model` next
    to it). Put it back into the game with 26Viewer (Edit Mode ▸ Replace).
  - Every material slot of an imported mesh is one part of the model; its faces become
    that part's new geometry: move, add or delete vertices and faces, re-UV, repaint
    vertex colours. A slot left with no faces removes the part. Parts you didn't import
    (or whose object you deleted) stay as they were.
  - Detail levels: an imported `LOD1`–`LOD3` mesh is used for its level; without one, the
    edit of LOD0 is drawn at the lower levels too.
  - What Blender doesn't show (damage offsets on cars, bone weights on characters) is
    kept from the original vertex, or copied from the nearest one for new vertices.
    Unmoved vertices keep their exact normals until you *Clear Custom Split Normals*.
  - Not yet: new parts / new material slots, other effects or textures, moving parts
    (element placement), collision.

The preview inside the node group is an approximation (Principled BSDF with the colour
texture, normal map and alpha); the game's own shaders aren't reproduced. Paint has no
texture: Blur picks the paint colour itself.

## Install

1. Zip the repository folder (or use Blender's *Build Extension*), then in Blender:
   *Edit ▸ Preferences ▸ Get Extensions ▸ ⌄ ▸ Install from Disk…* and pick the zip.
2. Get `.model` files out of the game's archives with
   [26Viewer](https://github.com/C6G3/26Viewer) (select ▸ Extract).

Requires Blender 5.0 or newer.

## Roadmap

1. ✅ Import: geometry, hierarchy, materials, textures, detail levels, shadow hulls.
2. ✅ Blur material presets (106 effects from every model in the game).
3. ✅ The scene stream (`Render/Scene`, an "ARCH" serialized object graph) read and
   written back byte for byte for all 1,744 models (`blur/scene.py`, field order from
   Blur.exe's loader).
4. ✅ Export of edited geometry for existing parts, every detail level, shadow hulls.
5. ⏳ Textures (replace / add) and changing a part's effect and parameters.
6. New parts and models made from scratch (new geometry records, material entries and
   value sets).
7. Collision (`Coll`), damage bones, skinning to `.skeleton` bones.

## Layout

| Path | What |
|---|---|
| `blur/` | The format code (plain Python + numpy, no Blender needed): chunk files, models, the scene stream (`scene.py`), parts and buffer rebuilding (`parts.py`), DDS |
| `importer.py`, `exporter.py`, `materials.py`, `__init__.py` | The Blender side |
| `presets/effects.json` | Every Blur effect's passes, inputs, usual values and textures |
| `tools/scan_effects.py` | Rebuilds `effects.json` from the game (`python tools/scan_effects.py F:/Games/BLUR`) |
| `tools/check_all_models.py` | Reads every model in the game (sanity check of `blur/model.py`) |
| `tools/check_scene.py` | Reads and rewrites every model's scene stream; must come out byte for byte |
| `tools/check_parts.py` | Rebuilds every model's buffers from its own parts; must draw the same |
| `tools/blender_test.py` | Imports a model in a background Blender and renders a picture |
| `tools/blender_export_test.py` | Imports, exports unchanged and with a part scaled, and compares |

## License

MIT — see [LICENSE](LICENSE).
