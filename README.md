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
  click **Choose Blur Effect…** and pick one of the game's 106 effects (`veh_Paint_a`,
  `veh_Glass_c_h`, `veh_Default_b_f`, `default_NL_NV`, `MeshEffect`…). The material gets a
  **Blur Shader** node group with one socket per input the game gives that effect, plus an
  Image Texture node for each texture slot. Pick images in the panel; the panel also shows
  which textures the game normally uses in each slot and the effect's parameters
  (`g_vMtlParameters`…) with the game's usual values. Switching to another effect keeps the
  images already plugged in.
- **Export**: not yet (see the roadmap below).

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
3. ⏳ Export: writing the model's scene stream (`Render/Scene`, an "ARCH" serialized
   object graph). The records the game reads are being mapped from Blur.exe's own loader.
   First target: write a model back with edited parts, materials and textures; then
   models made from scratch in Blender.
4. Collision (`Coll`), damage bones, skinning to `.skeleton` bones.

## Layout

| Path | What |
|---|---|
| `blur/` | The format readers (plain Python, no Blender needed): chunk files, models, DDS |
| `importer.py`, `materials.py`, `__init__.py` | The Blender side |
| `presets/effects.json` | Every Blur effect's passes, inputs, usual values and textures |
| `tools/scan_effects.py` | Rebuilds `effects.json` from the game (`python tools/scan_effects.py F:/Games/BLUR`) |
| `tools/check_all_models.py` | Reads every model in the game (sanity check of `blur/model.py`) |
| `tools/blender_test.py` | Imports a model in a background Blender and renders a picture |

## License

MIT — see [LICENSE](LICENSE).
