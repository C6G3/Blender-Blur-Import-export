"""Writes BLUR_MATERIALS.md: every Blur material (effect), what it's for and where the game uses it.

    python tools/make_materials_doc.py

Hand-written explanations (families, name letters, inputs) are below; the per-effect
facts (counts, kinds of model, part names, textures, usual values) come from
presets/effects.json (tools/scan_effects.py, from every model in the game).
"""

import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")

INTRO = """# Blur materials

Every part of a Blur model is drawn with an **effect** (a compiled shader, `veh_Paint_a_b_c.fx`,
`default_NB_NL_NV.fx`…) and a set of **inputs** for it: textures and numbers. In Blender a Blur
material is one node group per effect (*Material Properties ▸ Blur Material ▸ Choose Blur
Effect…*) with a socket per input; this page explains them all.

Everything here comes from the game's own files: the effect and input names, which parts use
which effect, the usual values and textures (scanned from all 1,744 models by
`tools/scan_effects.py`), and the meaning of the name letters (from the compiled shaders: each
letter removes the same inputs and vertex data in every family). Descriptions of what an effect
*looks like* are inferred from where the game uses it.

- [How an effect name is built](#how-an-effect-name-is-built)
- [Inputs](#inputs)
- [Vehicle effects](#vehicle-effects)
- [World and prop effects](#world-and-prop-effects)
- [Character effects](#character-effects)
- [Power-ups and special effects](#power-ups-and-special-effects)
- [Every effect](#every-effect)

## How an effect name is built

`family_letters.fx`. The family is the kind of surface; each letter **switches a feature off**,
so `veh_Default_b_c_f_h` is the Default car shader without bump map (b), damage control
points (c), scratches (f) and damage offsets (h). The game ships the shader for every
combination; models use the ones in [Every effect](#every-effect).

**Vehicle letters** (`veh_…`; checked against every compiled vehicle shader and every car part):

| Letter | Switches off | Input / vertex data it removes |
|---|---|---|
| `a` | the part's colour texture | `g_MeshTexture` (the part gets a plain colour) |
| `b` | the bump (normal) map | `g_BumpTexture` |
| `c` | damage control points: the part doesn't bend with the car's damage volume | vertex texture coordinates 4 (control point numbers) |
| `d` | (glass) the dent / crack normal map | `g_DentTexture` |
| `f` | scratches | `g_ScratchTexture` |
| `g` | (neon) the damaged texture | `g_DamageTexture` |
| `h` | damage offsets: the part doesn't crumple | vertex texture coordinates 2 and 3 (position / normal offsets) |
| `ln` | (only in the shader files, no model uses it) | — |

Wheels (`veh_Alloy`) and shadow hulls never carry damage data.

**World and character tags** (`default_…`, `HighVis_…`; checked against every model's inputs and
vertex data):

| Tag | Means | Effect on inputs / vertices |
|---|---|---|
| `NB` | no bump | no `g_tNormal` normal map |
| `NM` | no material map | no `g_tMaterial` |
| `NV` | no vertex colour | the vertices have no colour |
| `NL` | no lightmap | lit by the game's light probes instead of a baked `g_tLightmap` (only `default_NB_NV`, an older barrier, has one) |
| `skin` | skinned | vertices carry 4 bone numbers and weights; `g_mPalette` lists the bones |

## Inputs

**Textures** (an Image Texture node per slot in Blender; the game may share one texture between
many slots):

| Input | What it is |
|---|---|
| `g_MeshTexture` | Car part colour texture (badges, interior, grilles, lights, tyres…); its alpha is the transparency on Alpha / Glass parts |
| `g_BumpTexture` | Car normal map (`*_nrm`, `bump`) |
| `g_DentTexture` | Damage normal map faded in as the part is hit: `paintdent` on paint, `smashedglass_nrm` (cracks) on glass |
| `g_ScratchTexture` | Scratch mask: where damage scrapes the paint off to the undercoat / scuff colour; `smashedglass` (the shattered pattern) on glass. `DefaultColour` = no scratches |
| `g_DamageTexture` | Neon: the texture shown once the part is damaged |
| `g_sOffTexture`, `g_sOnTexture` | Lights: the lamp unlit and lit (the game switches them for headlights, brake lights, indicators) |
| `g_sOffTextureDamage`, `g_sOnTextureDamage` | the same once the lamp is broken |
| `g_tAlbedo` | World / character colour texture (`*_diff`, `*_skin`) |
| `g_tMaterial` | Material map (`*_ipr0`): shine / reflection mask; `DefaultColour` = plain |
| `g_tNormal` | World normal map |
| `g_tNeon` | Glow texture (neon signs, traffic lights) |
| `g_tLightmap` | Baked lighting (second UV set) |
| `g_tTexture`, `g_2L_tTexture` | Power-up / effect texture, and its second layer |
| `g_tUVDistortTexture`, `g_2L_tUVDistortTexture` | Pattern that warps the effect texture's UVs |
| `g_tBlendNormal` | Water: second normal map blended over the first |
| `g_tColour` | Light flare sprite |

**Numbers** (sockets in the node group; a 4- or 8-value input shows as `name 0`, `name 1`…):

| Input | Meaning |
|---|---|
| `g_vMtlParameters` | Car material: 0 reflectivity facing you, 1 reflectivity at grazing angles (the "fresnel" edge), 2 bump strength, 3 dent strength, 4 base colour amount (lights 1); 5–7 unused. Names from the compiled shaders' parameter table |
| `g_MattParams` | Matt / alloy: 0 specular, 3 shininess |
| `g_fReflectorIntensity`, `g_fEmissiveIntensity` | High-visibility reflectors: how bright they catch headlights, and their own glow |
| `g_fNeonRange`, `g_fNeonNearIntensity`, `g_fNeonFarIntensity`, `g_fTint` | High-vis barriers' glow and its fade with distance |
| `g_vAnimatedNeonColour`, `g_fAnimatedNeonY`, `g_fScrollSpeedX/Y` | Animated neon: colour and how the glow texture scrolls |
| `g_vColour`, `g_vColourFresnel`, `g_vFresnelPower` | Effect colour, colour at the edges, and how sharp the edge is |
| `g_vScrollTextureX/Y`, `g_vSpeedScrollTextureX/Y` | Effect texture offset and scroll speed (per layer: `g_2L_…`) |
| `gUvDistort`, `gUvScrollDistortScale`, `gUvScrollDistortOffsetX/Y` | UV distortion strength, scale and offset |
| `g_pRefractionIntensity`, `g_vRefractColour`, `g_vRefractColourFresnel` | Refraction strength and tint |
| `g_vLightFlareColour`, `g_fLightFlareIntensity`, `g_fLightFlareSize` | Flare colour, brightness and size |
| `g_fFrequency`, `g_fThresholdOn`, `g_fThresholdOff` | Flashing flares: blink rate and on/off points |
| `g_vWaterColour`, `g_fWaterSpecularIntensity`, `g_fWaterRefractAmount`, `g_fWaterExtinctionScale`, `g_vNormalScale0/1`, `g_vNormalVelocity0/1`, `g_fRippleIntensity` | Water look and wave movement |
| `g_fScrollX/Y`, `g_fScrollSpeedX/Y` | Scrolling textures (tides, sprays) |

**Data inputs** are filled in by the game while it runs and have no socket: the lighting around
the car (`g_LocalSpaceSHNode`, `VehicleSHNode`), damage (`g_vCodeDamageScale` on most parts),
bones (`g_mPalette`) and animation (`g_fAnimatedNeonX`).

**Passes.** Most car effects draw in three passes: the main one (the inputs above), an
empty one, and a lighting pass with the data inputs. Blender shows the main pass; the
exporter keeps the others as they are.
"""

FAMILIES = [
    ("Vehicle effects", [
        ("veh_Paint", "Body paint. **No colour texture**: Blur paints it with the colour (or livery) chosen for the "
                      "car, so in Blender the viewport colour is only a preview. Dents and scratches show damage."),
        ("veh_Default", "Everything textured on a car that isn't paint: interior, dashboard, engine bay, grilles, "
                        "badges, brake discs and calipers, mirrors, wipers."),
        ("veh_Matt", "Matt surfaces, above all tyres (`tyrewall`, `tyretred` + normal maps); also trim."),
        ("veh_Alloy", "Wheel rims (and some metal trim): shiny metal, no damage data."),
        ("veh_Glass", "Windows and lamp covers. The colour texture's alpha gives tint and opaque areas; on "
                      "damage the crack normal map and shattered pattern appear."),
        ("veh_Light", "Head, tail, brake, reverse and indicator lamps: separate unlit / lit textures the game "
                      "switches, and broken versions."),
        ("veh_Neon", "Self-lit parts, mainly licence plates (`cali_…`, `uk_…` plate textures)."),
        ("veh_Alpha", "Transparent or cut-out details: decals, stickers, mesh grilles."),
        ("veh_Shadow", "The shadow hull: a simple closed mesh (positions only) the game draws the car's shadow "
                       "with. Imported into the hidden *Shadow* collection."),
    ]),
    ("World and prop effects", [
        ("default", "Props and buildings: colour texture, usually a material map, sometimes a normal map. "
                    "`default_NB_NL_NV` and `default_NB_NL_NM_NV` cover most props."),
        ("HighVis", "High-visibility signs and barriers: reflectors that light up in headlights."),
        ("HighVisBarrier", "Construction barriers with glowing strips."),
        ("AnimatedNeon", "Traffic lights, lamp posts and signs with animated glow."),
        ("ScrollUVNeon", "Neon with a scrolling texture."),
        ("ScrollFade", "Scrolling, fading surfaces: tides on the beach, hydrant spray (also skinned)."),
        ("Water", "Rivers / water planes."),
        ("Ocean", "The sea."),
        ("Puddle", "Puddles."),
    ]),
    ("Character effects", [
        ("default_skin", "Drivers and crowd: skinned to a `.skeleton`'s bones."),
    ]),
    ("Power-ups and special effects", [
        ("MeshEffect", "Power-ups (shields, bolts, mines, pickups), their trails and the start / finish line "
                       "effects: glowing, usually additive, scrolling textures. Name words: `Cull` hides back "
                       "faces, `NoDepth` / `NDepth` draws over everything (no depth test), `DLayer` adds a second "
                       "texture layer (`g_2L_…`), `UVDist(ort)` warps the UVs with a distortion texture, "
                       "`Refract` bends what is behind."),
        ("LightFlare", "Light flares on lamps and emergency lights (sprite + colour + size); `SoftLightFlare` "
                       "fades softly, `FlashingLightFlare` blinks, `CarLightFlare` is the cars' lamp flare."),
        ("ScreenFacingSprite", "Sprites that always face the camera."),
    ]),
]

TYPE_WORDS = {"texture": "texture", "texture_ptr": "texture", "f32": "number", "data": "set by the game",
              "material": "material", "s8": "integer", "u8": "integer", "s16": "integer", "u16": "integer",
              "s32": "integer", "u32": "integer"}
VERTEX = {(0, 0): "position", (3, 0): "normal", (9, 0): "colour", (5, 0): "UV", (5, 1): "UV 2",
          (5, 2): "damage offsets", (5, 3): "damage offsets", (5, 4): "damage control points"}
SKINNED = {(5, 3): "bone numbers", (5, 4): "bone weights"}


def family_of(effect):
    low = effect.lower()
    for _, fams in FAMILIES:
        for fam, _ in sorted(fams, key=lambda f: -len(f[0])):
            if low.startswith(fam.lower()):
                return fam
    return None


def fmt_values(v):
    return ", ".join(f"{x:g}" if isinstance(x, float) else str(x) for x in v)


def main():
    with open(os.path.join(ROOT, "presets", "effects.json"), encoding="utf-8") as fh:
        effects = json.load(fh)
    out = [INTRO]
    for title, fams in FAMILIES:
        out.append(f"## {title}\n")
        out.append("| Family | Used for | Effects in the game |")
        out.append("|---|---|---|")
        for fam, text in fams:
            names = sorted((e for e in effects if family_of(e) == fam), key=str.lower)
            links = ", ".join(f"[`{n[:-3]}`](#{n[:-3].lower().replace('_', '_')})" for n in names) or "—"
            out.append(f"| `{fam}` | {text} | {links} |")
        out.append("")

    out.append("## Every effect\n")
    out.append("Counts are over all 1,744 models. *Kinds of model* say where the game uses it; *parts* are "
               "the most common element names it's drawn on.\n")
    for name in sorted(effects, key=str.lower):
        e = effects[name]
        out.append(f"### {name[:-3]}\n")
        where = ", ".join(f"{k} ({n})" for k, n in e.get("where", []))
        out.append(f"- **Used on** {e['parts']} part(s) in {e['models']} model(s): {where or '—'}")
        if e.get("elements"):
            out.append(f"- **Parts**: {', '.join('`' + x + '`' for x in e['elements'][:10])}")
        if e.get("examples"):
            out.append(f"- **For example** {', '.join('`' + x + '`' for x in e['examples'][:4])}")
        vertex = []
        for v in e.get("vertex", []):
            key = (v["usage"], v["index"])
            label = SKINNED.get(key) if e.get("skinned") and key in SKINNED else VERTEX.get(key)
            if label and label not in vertex:
                vertex.append(label)
        if vertex:
            out.append(f"- **Vertex data**: {', '.join(vertex)}" + (" (skinned)" if e.get("skinned") else ""))
        inputs = e["passes"][0]["inputs"] if e["passes"] else []
        if inputs:
            out.append("\n| Input | Kind | Usual value / textures |")
            out.append("|---|---|---|")
            for i in inputs:
                kind = TYPE_WORDS.get(i["type"], i["type"])
                if i["count"] > 1:
                    kind += f" × {i['count']}"
                usual = ""
                if i["name"] in e.get("textures", {}):
                    usual = ", ".join(f"`{t}`" for t in e["textures"][i["name"]][:4])
                elif i["name"] in e.get("defaults", {}):
                    usual = fmt_values(e["defaults"][i["name"]])
                out.append(f"| `{i['name']}` | {kind} | {usual} |")
        extra = [p for p in e["passes"][1:] if p["inputs"]]
        for p in extra:
            out.append(f"\nAlso a pass with {', '.join('`' + i['name'] + '`' for i in p['inputs'])} "
                       "(set by the game).")
        out.append("")
    with open(os.path.join(ROOT, "BLUR_MATERIALS.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print("wrote BLUR_MATERIALS.md,", len(effects), "effects")


if __name__ == "__main__":
    main()
