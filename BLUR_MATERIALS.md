# Blur materials

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

## Vehicle effects

| Family | Used for | Effects in the game |
|---|---|---|
| `veh_Paint` | Body paint. **No colour texture**: Blur paints it with the colour (or livery) chosen for the car, so in Blender the viewport colour is only a preview. Dents and scratches show damage. | [`veh_paint`](#veh_paint), [`veh_Paint_a`](#veh_paint_a), [`veh_Paint_a_b`](#veh_paint_a_b), [`veh_Paint_a_b_c`](#veh_paint_a_b_c), [`veh_Paint_a_b_c_h`](#veh_paint_a_b_c_h), [`veh_Paint_a_b_h`](#veh_paint_a_b_h), [`veh_Paint_a_c`](#veh_paint_a_c), [`veh_Paint_a_c_h`](#veh_paint_a_c_h), [`veh_paint_b`](#veh_paint_b), [`veh_paint_b_c`](#veh_paint_b_c), [`veh_Paint_b_c_h`](#veh_paint_b_c_h), [`veh_paint_c`](#veh_paint_c) |
| `veh_Default` | Everything textured on a car that isn't paint: interior, dashboard, engine bay, grilles, badges, brake discs and calipers, mirrors, wipers. | [`veh_Default_a_b`](#veh_default_a_b), [`veh_Default_a_b_c`](#veh_default_a_b_c), [`veh_Default_a_b_c_f`](#veh_default_a_b_c_f), [`veh_Default_a_b_c_f_h`](#veh_default_a_b_c_f_h), [`veh_Default_a_b_c_h`](#veh_default_a_b_c_h), [`veh_Default_a_b_f`](#veh_default_a_b_f), [`veh_Default_a_b_f_h`](#veh_default_a_b_f_h), [`veh_Default_a_b_h`](#veh_default_a_b_h), [`veh_Default_a_c`](#veh_default_a_c), [`veh_Default_a_c_f`](#veh_default_a_c_f), [`veh_Default_a_c_f_h`](#veh_default_a_c_f_h), [`veh_Default_a_c_h`](#veh_default_a_c_h), [`veh_Default_b`](#veh_default_b), [`veh_Default_b_c`](#veh_default_b_c), [`veh_Default_b_c_f`](#veh_default_b_c_f), [`veh_Default_b_c_f_h`](#veh_default_b_c_f_h), [`veh_Default_b_c_h`](#veh_default_b_c_h), [`veh_Default_b_f`](#veh_default_b_f), [`veh_Default_b_f_h`](#veh_default_b_f_h), [`veh_Default_c`](#veh_default_c), [`veh_Default_c_f`](#veh_default_c_f), [`veh_Default_c_f_h`](#veh_default_c_f_h), [`veh_Default_f`](#veh_default_f) |
| `veh_Matt` | Matt surfaces, above all tyres (`tyrewall`, `tyretred` + normal maps); also trim. | [`veh_Matt_a_b_c_f`](#veh_matt_a_b_c_f), [`veh_Matt_a_b_c_f_h`](#veh_matt_a_b_c_f_h), [`veh_Matt_a_b_f`](#veh_matt_a_b_f), [`veh_Matt_a_b_f_h`](#veh_matt_a_b_f_h), [`veh_Matt_b`](#veh_matt_b), [`veh_Matt_b_c_f`](#veh_matt_b_c_f), [`veh_Matt_b_c_f_h`](#veh_matt_b_c_f_h), [`veh_Matt_b_f`](#veh_matt_b_f), [`veh_Matt_b_f_h`](#veh_matt_b_f_h), [`veh_Matt_c_f`](#veh_matt_c_f), [`veh_Matt_c_f_h`](#veh_matt_c_f_h), [`veh_Matt_f`](#veh_matt_f) |
| `veh_Alloy` | Wheel rims (and some metal trim): shiny metal, no damage data. | [`veh_Alloy_a_b_f`](#veh_alloy_a_b_f), [`veh_Alloy_a_f`](#veh_alloy_a_f), [`veh_Alloy_b_f`](#veh_alloy_b_f), [`veh_Alloy_f`](#veh_alloy_f) |
| `veh_Glass` | Windows and lamp covers. The colour texture's alpha gives tint and opaque areas; on damage the crack normal map and shattered pattern appear. | [`veh_Glass_a_c`](#veh_glass_a_c), [`veh_Glass_a_c_d`](#veh_glass_a_c_d), [`veh_Glass_a_c_d_h`](#veh_glass_a_c_d_h), [`veh_Glass_a_c_h`](#veh_glass_a_c_h), [`veh_Glass_c`](#veh_glass_c), [`veh_Glass_c_d`](#veh_glass_c_d), [`veh_Glass_c_d_h`](#veh_glass_c_d_h), [`veh_Glass_c_h`](#veh_glass_c_h), [`veh_Glass_d`](#veh_glass_d) |
| `veh_Light` | Head, tail, brake, reverse and indicator lamps: separate unlit / lit textures the game switches, and broken versions. | [`veh_Light_c`](#veh_light_c), [`veh_Light_c_h`](#veh_light_c_h) |
| `veh_Neon` | Self-lit parts, mainly licence plates (`cali_…`, `uk_…` plate textures). | [`veh_Neon_c`](#veh_neon_c), [`veh_Neon_c_g`](#veh_neon_c_g), [`veh_Neon_c_g_h`](#veh_neon_c_g_h), [`veh_Neon_c_h`](#veh_neon_c_h) |
| `veh_Alpha` | Transparent or cut-out details: decals, stickers, mesh grilles. | [`veh_Alpha`](#veh_alpha), [`veh_Alpha_c`](#veh_alpha_c), [`veh_Alpha_c_h`](#veh_alpha_c_h) |
| `veh_Shadow` | The shadow hull: a simple closed mesh (positions only) the game draws the car's shadow with. Imported into the hidden *Shadow* collection. | [`veh_Shadow`](#veh_shadow) |

## World and prop effects

| Family | Used for | Effects in the game |
|---|---|---|
| `default` | Props and buildings: colour texture, usually a material map, sometimes a normal map. `default_NB_NL_NV` and `default_NB_NL_NM_NV` cover most props. | [`default_NB_NL`](#default_nb_nl), [`default_NB_NL_NM_NV`](#default_nb_nl_nm_nv), [`default_NB_NL_NV`](#default_nb_nl_nv), [`default_NL_NV`](#default_nl_nv), [`default_skin_NB_NL_NM_NV`](#default_skin_nb_nl_nm_nv), [`default_skin_NV`](#default_skin_nv) |
| `HighVis` | High-visibility signs and barriers: reflectors that light up in headlights. | [`HighVis_NB_NL_NV`](#highvis_nb_nl_nv) |
| `HighVisBarrier` | Construction barriers with glowing strips. | [`HighVisBarrier_NL_NV`](#highvisbarrier_nl_nv) |
| `AnimatedNeon` | Traffic lights, lamp posts and signs with animated glow. | [`AnimatedNeon_NL_NV`](#animatedneon_nl_nv) |
| `ScrollUVNeon` | Neon with a scrolling texture. | [`ScrollUVNeon_NV`](#scrolluvneon_nv) |
| `ScrollFade` | Scrolling, fading surfaces: tides on the beach, hydrant spray (also skinned). | [`ScrollFade_NL`](#scrollfade_nl), [`ScrollFade_skin_NL`](#scrollfade_skin_nl) |
| `Water` | Rivers / water planes. | [`Water_NL_NV`](#water_nl_nv) |
| `Ocean` | The sea. | [`Ocean_NL`](#ocean_nl) |
| `Puddle` | Puddles. | [`Puddle_NL_NV`](#puddle_nl_nv) |

## Character effects

| Family | Used for | Effects in the game |
|---|---|---|
| `default_skin` | Drivers and crowd: skinned to a `.skeleton`'s bones. | — |

## Power-ups and special effects

| Family | Used for | Effects in the game |
|---|---|---|
| `MeshEffect` | Power-ups (shields, bolts, mines, pickups), their trails and the start / finish line effects: glowing, usually additive, scrolling textures. Name words: `Cull` hides back faces, `NoDepth` / `NDepth` draws over everything (no depth test), `DLayer` adds a second texture layer (`g_2L_…`), `UVDist(ort)` warps the UVs with a distortion texture, `Refract` bends what is behind. | [`MeshEffect`](#mesheffect), [`MeshEffectCull`](#mesheffectcull), [`MeshEffectCullNoDepth`](#mesheffectcullnodepth), [`MeshEffectDLayer`](#mesheffectdlayer), [`MeshEffectDLayerCull`](#mesheffectdlayercull), [`MeshEffectDLayerCullNDepth`](#mesheffectdlayercullndepth), [`MeshEffectDLayerUVDist`](#mesheffectdlayeruvdist), [`MeshEffectDLayerUVDistCull`](#mesheffectdlayeruvdistcull), [`MeshEffectDLayerUVDistCullNDepth`](#mesheffectdlayeruvdistcullndepth), [`MeshEffectDLayerUVDistNDepth`](#mesheffectdlayeruvdistndepth), [`MeshEffectNoDepth`](#mesheffectnodepth), [`MeshEffectRefract`](#mesheffectrefract), [`MeshEffectUVDistort`](#mesheffectuvdistort), [`MeshEffectUVDistortCull`](#mesheffectuvdistortcull), [`MeshEffectUVDistortCullNoDepth`](#mesheffectuvdistortcullnodepth), [`MeshEffectUVDistortNoDepth`](#mesheffectuvdistortnodepth) |
| `LightFlare` | Light flares on lamps and emergency lights (sprite + colour + size); `SoftLightFlare` fades softly, `FlashingLightFlare` blinks, `CarLightFlare` is the cars' lamp flare. | [`LightFlare`](#lightflare) |
| `ScreenFacingSprite` | Sprites that always face the camera. | [`ScreenFacingSprite`](#screenfacingsprite) |

## Every effect

Counts are over all 1,744 models. *Kinds of model* say where the game uses it; *parts* are the most common element names it's drawn on.

### AnimatedNeon_NL_NV

- **Used on** 44 part(s) in 14 model(s): objects: uk_london_hackney (7), objects: uk_brighton (2), special effects (2), objects: shared (1), objects: usa_amboy (1), objects: usa_la_longbeachdocks (1)
- **Parts**: `defaultelement`, `o_trafficlighttyped`, `o_trafficlighttypeb`, `s_trafficlighttypea_head`, `o_trafficlighttypea`, `o_trafficlighttypee`, `o_trafficlighttypef`, `m_trafficcone_light`, `o_trafficlighttypec`, `m_ferriswheel`
- **For example** `trafficlighttypef.model`, `trafficlighttyped.model`, `trafficlighttypea.model`, `trafficlighttypee.model`
- **Vertex data**: position, normal, UV, damage offsets

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tNeon` | texture | `trafficlightcrop_animatedneon`, `lampposta_neon`, `trafficcone01_light_neon`, `flashingcrossing_neon` |
| `g_tAlbedo` | texture | `trafficlightcrop_diff`, `lampposta_diff`, `trafficcone01_light_diff`, `lampposte_diff` |
| `g_tMaterial` | texture | `DefaultColour` |
| `g_fAnimatedNeonY` | number × 4 | 0, 0, 0, 0 |
| `g_fAnimatedNeonX` | set by the game |  |
| `g_vAnimatedNeonColour` | number × 4 | 1, 1, 1, 0 |
| `g_fScrollSpeedX` | number × 4 | 0, 0, 0, 0 |
| `g_fScrollSpeedY` | number × 4 | 0, 0, 0, 0 |

### CarLightFlare

- **Used on** 1 part(s) in 1 model(s): system (1)
- **Parts**: `defaultelement`
- **For example** `carlightflare.model`
- **Vertex data**: position, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tColour` | texture | `lightflare_diff` |
| `g_vLightFlareColour` | set by the game |  |
| `g_fLightFlareIntensity` | set by the game |  |
| `g_fLightFlareSize` | set by the game |  |

### default_NB_NL

- **Used on** 25 part(s) in 3 model(s): objects: usa_sanfran_sausalito (3)
- **Parts**: `s_damaged06_d1`, `o_directionsigna`, `s_damage06_d1`, `s_damage07_d2`, `s_damage05_d3`, `o_directionsignb`, `o_directionsignc`, `s_signdam_d1`, `s_damage03_d5`, `s_damaged02_d3`
- **For example** `directionsigna.model`, `directionsignb.model`, `directionsignc.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `DirectionSignA_DIFF`, `DirectionSignB_DIFF`, `DirectionSignC_DIFF` |
| `g_tMaterial` | texture | `DirectionSignA_IPR0`, `DirectionSignB_IPR0`, `DirectionSignC_IPR0` |

### default_NB_NL_NM_NV

- **Used on** 1628 part(s) in 378 model(s): objects: shared (115), objects: usa_la_river (65), objects: spa_barcelona_gracia (57), objects: uk_brighton (29), objects: usa_la_downtown (20), objects: usa_amboy (17), objects: uk_london_hackney (16), objects: usa_la_longbeachdocks (16), objects: jpn_mountaintrack (15), special effects (12), objects: usa_sanfran_russianhill (6), objects: jpn_shutoko (5), objects: usa_la_observatory (3), characters (1), objects: usa_ny_dumbo (1)
- **Parts**: `defaultelement`, `s_main_d1`, `s_sign_d2`, `s_pole_d1`, `o_busstop`, `s_smlsizedvan_damage`, `s_trackmiddledoublebridgeunit_metal_piece2`, `s_lampostc_head`, `s_sign_d1`, `s_main_fence_d1`
- **For example** `birds02.model`, `birds01.model`, `busstop.model`, `ny_trackmiddledoublebridgeunit.model`
- **Vertex data**: position, normal, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `DefaultColour`, `dynamicobjects01_diff`, `dove_diff`, `black` |

### default_NB_NL_NV

- **Used on** 2585 part(s) in 674 model(s): objects: shared (140), objects: usa_la_longbeachdocks (123), objects: usa_la_downtown (109), objects: uk_london_hackney (103), objects: jpn_shutoko (63), objects: uk_brighton (42), objects: usa_la_observatory (21), objects: usa_amboy (20), objects: usa_la_river (13), objects: usa_ny_dumbo (12), objects: spa_barcelona_gracia (8), special effects (6), objects: usa_sanfran_russianhill (5), objects: usa_sanfran_sausalito (4), models (2), objects: jpn_mountaintrack (1), objects: spa_barcelona_oval (1), system (1)
- **Parts**: `defaultelement`, `s_base_d1`, `s_main_d1`, `s_pole_d1`, `o_streetlamp14`, `s_bottom_d2`, `o_lamposta`, `o_smlsizedvan`, `o_lampostc`, `s_lampostc_head`
- **For example** `windmill01.model`, `lamposta.model`, `vehicletransporter.model`, `bluetransit.model`
- **Vertex data**: position, normal, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `dynamicwoodenpallet_diff`, `cab01alphas_diff`, `streetlamp09_diff`, `lampostabcd_diff` |
| `g_tMaterial` | texture | `dynamicwoodenpallet_ipr0`, `cab01alphas_ipr0`, `streetlamp09_ipr0`, `lampostabcd_ipr0` |

### default_NL_NV

- **Used on** 21 part(s) in 4 model(s): objects: uk_brighton (2), models (1), special effects (1)
- **Parts**: `o_sunlounger`, `s_sunlounger_brokenpiece5`, `s_sunlounger_brokenpiece4`, `o_rowingboat01`, `e_fanblades`, `s_sunlounger_brokenpiece7`, `s_sunlounger_brokenpiece3`, `s_sunlounger_brokenpiece2`, `s_sunlounger_brokenpiece1`, `s_sunlounger_brokenpiece6`
- **For example** `sunlounger.model`, `rowingboat01.model`, `fanblades.model`, `shsphere.model`
- **Vertex data**: position, normal, UV, UV 2

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `sunlounger_pt_diff`, `rowingboat01_diff`, `ships_surface2_diff`, `grey_diff` |
| `g_tMaterial` | texture | `sunlounger_pt_ipr0`, `rowingboat01_ipr0`, `ships_surface2_ipr0`, `grey_ipr0` |
| `g_tNormal` | texture | `sunlounger_pt_norm`, `rowingboat01_norm`, `ships_surface2_norm`, `grey_norm` |

### default_skin_NB_NL_NM_NV

- **Used on** 1874 part(s) in 96 model(s): characters (96)
- **Parts**: `defaultelement`
- **For example** `igm_sanfran_minor6.model`, `igm_sanfran_minor5.model`, `igm_hackney_minor3.model`, `igm_ny_minor4.model`
- **Vertex data**: position, normal, UV, bone numbers, bone weights (skinned)

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `mcrd_arms1_skin`, `fcrd_arm2_skin`, `mcrd_arms3_skin`, `fcrd_arm10_skin` |

Also a pass with `g_mPalette` (set by the game).

### default_skin_NV

- **Used on** 2 part(s) in 1 model(s): characters (1)
- **Parts**: `defaultelement`
- **For example** `n01.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, damage control points

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_mPalette` | set by the game × 23 |  |
| `g_tAlbedo` | texture | `LOW_No1_Cropsheet_DIFF` |
| `g_tMaterial` | texture | `LOW_No1_Cropsheet_IPR0` |
| `g_tNormal` | texture | `LOW_No1_Cropsheet_NORM` |

### FlashingLightFlare

- **Used on** 2 part(s) in 2 model(s): objects: usa_amboy (1), objects: usa_la_longbeachdocks (1)
- **Parts**: `defaultelement`, `o_airfieldlight_01`
- **For example** `gantrycabcontainer.model`, `airfieldlight_01.model`
- **Vertex data**: position, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tColour` | texture | `lightflare_diff` |
| `g_vLightFlareColour` | number × 4 | 0.91, 0.1118, 0.00364, 0 |
| `g_fLightFlareIntensity` | number × 4 | 1, 0, 0, 0 |
| `g_fLightFlareSize` | number × 4 | 1, 0, 0, 0 |
| `g_fFrequency` | number × 4 | 1, 0, 0, 0 |
| `g_fThresholdOn` | number × 4 | 1, 0, 0, 0 |
| `g_fThresholdOff` | number × 4 | 0, 0, 0, 0 |

### HighVis_NB_NL_NV

- **Used on** 43 part(s) in 19 model(s): objects: shared (11), objects: usa_amboy (3), objects: uk_brighton (2), objects: usa_la_downtown (2), objects: usa_la_longbeachdocks (1)
- **Parts**: `defaultelement`, `o_barrier1`, `s_barrier1_base_dam_d1`, `o_barrier2`, `s_barrier2_base_d1`, `o_small_caresign`, `s_wood_b_l_d2`, `s_wood_b_r_d1`, `m_trafficcone_light`, `s_barrier1_toprpeg_dam_d5`
- **For example** `small_caresign.model`, `barrier1.model`, `barrier2.model`, `traffic_cone01_light.model`
- **Vertex data**: position, normal, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `highvis_barrier2_diff`, `smallcarebarrier_diff`, `trafficcone01_diff`, `ambient_smallsign_diff` |
| `g_tMaterial` | texture | `highvis_barrier2_ipr0`, `smallcarebarrier_ipr0`, `DefaultColour`, `trafficcone01_ipr0` |
| `g_fReflectorIntensity` | number × 4 | 20, 0, 0, 0 |
| `g_fEmissiveIntensity` | number × 4 | 1, 0, 0, 0 |

### HighVisBarrier_NL_NV

- **Used on** 12 part(s) in 3 model(s): objects: shared (3)
- **Parts**: `defaultelement`, `o_road_barrier`, `s_leg_r_d5`, `s_leg_l_d4`, `s_road_barrier_dam_l_d3`, `s_road_barrier_dam_r_d1`, `s_road_barrier_dam_m_d2`
- **For example** `road_barrier01.model`, `highway_barrell.model`, `traffic_cone_hviz.model`
- **Vertex data**: position, normal, UV, UV 2

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_fNeonRange` | number × 4 | 100, 0, 0, 0 |
| `g_tAlbedo` | texture | `road_barrier01_diff`, `highway_barrell_diff`, `trafficcone01_light_diff` |
| `g_tMaterial` | texture | `road_barrier01_ipr0`, `highway_barrell_ipr0`, `DefaultColour` |
| `g_tNormal` | texture | `DefaultColour` |
| `g_fTint` | number × 4 | 1, 1, 1, 0 |
| `g_fReflectorIntensity` | number × 4 | 20, 0, 0, 0 |
| `g_fNeonFarIntensity` | number × 4 | 0, 0, 0, 0 |
| `g_fNeonNearIntensity` | number × 4 | 0, 0, 0, 0 |

### LightFlare

- **Used on** 75 part(s) in 59 model(s): objects: usa_la_downtown (12), objects: shared (10), objects: uk_london_hackney (9), special effects (8), objects: uk_brighton (5), objects: spa_barcelona_gracia (4), objects: usa_sanfran_russianhill (4), objects: jpn_shutoko (3), objects: usa_la_longbeachdocks (2), objects: spa_barcelona_oval (1), objects: usa_amboy (1)
- **Parts**: `defaultelement`, `o_lampostc`, `o_lamposta`, `e_police_lights1`, `e_police_lights2`, `o_streetlamp09`, `o_modernmetalliclamppostcurved`, `o_streetlamp07`, `o_lampostb`, `o_modernmetalliclamppoststraight`
- **For example** `police_flashing_lights.model`, `fire_engine_lights.model`, `lamposta.model`, `corner_arrows.model`
- **Vertex data**: position, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tColour` | texture | `lightflare_diff`, `light_flare_red`, `light_flare_white`, `light_flare_blue` |
| `g_vLightFlareColour` | number × 4 | 1, 1, 1, 0 |
| `g_fLightFlareIntensity` | number × 4 | 1, 0, 0, 0 |
| `g_fLightFlareSize` | number × 4 | 1, 0, 0, 0 |

### MeshEffect

- **Used on** 267 part(s) in 114 model(s): power-ups (perks) (77), special effects (29), objects: uk_london_hackney (7), objects: usa_la_downtown (1)
- **Parts**: `defaultelement`, `e_pasted__pasted__pplane2`, `e_pplane1`, `e_beam_2`, `e_beam_1`, `e_polysurface8`, `e_pplane2`, `e_beam1`, `e_polysurface11`, `e_pplane4`
- **For example** `direction_ambient_spot_01.model`, `shieldsuper.model`, `shieldsuperbumper.model`, `direction_corner_beam_ccw.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `revolvingbeam`, `light_lines_03`, `cloud_03`, `cloud_01` |
| `g_vColour` | number × 4 | -1, -1, -1, 0.5 |
| `g_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectCull

- **Used on** 14 part(s) in 5 model(s): power-ups (perks) (5)
- **Parts**: `e_barge_build_2`, `e_ring`, `e_wave1`
- **For example** `bargewave1left.model`, `splashdamagebargewave.model`, `minebuild1.model`, `shuntbuild2bumper.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `light_lines_04`, `mine_pulse_03`, `light_lines_15`, `light_paint_interfere_03` |
| `g_vColour` | set by the game |  |
| `g_vColourFresnel` | number × 4 | 1, 0.19767, 0, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectCullNoDepth

- **Used on** 32 part(s) in 13 model(s): power-ups (perks) (13)
- **Parts**: `defaultelement`, `e_cylinder1`, `e_barge_build_1`, `e_barge_build_2`
- **For example** `draftwind1.model`, `draftwindfadein1.model`, `draftwindfadeout1.model`, `shunt_flow_car_02.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `light_lines_08`, `light_lines_10`, `light_lines_09`, `light_lines_06` |
| `g_vColour` | set by the game | 1, 1, 1, 2 |
| `g_vColourFresnel` | set by the game | 1, 1, 1, 4 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectDLayer

- **Used on** 57 part(s) in 40 model(s): special effects (28), power-ups (perks) (12)
- **Parts**: `defaultelement`, `e_grafitti`, `e_swirl`, `e_phelix2`, `e_pplane2`
- **For example** `fangoldenpickup.model`, `fangoldenpickup_dimmed.model`, `repairzone1.model`, `blind_projectile_01.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `light_lines_02`, `light_lines_13`, `mine_pulse_02`, `mine_pulse_06` |
| `g_vColour` | number × 4 | 1, 1, 0.3, 1 |
| `g_vColourFresnel` | number × 4 | 0.5, 0.38333, 0.15, 0.25 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_tTexture` | texture | `light_lines_13`, `cloud_05`, `mine_pulse_06`, `DefaultColour` |
| `g_2L_vColour` | number × 4 | 1, 0.8, 0.6, 1 |
| `g_2L_vColourFresnel` | number × 4 | 1, 0.8, 0.6, 0.5 |
| `g_2L_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_2L_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectDLayerCull

- **Used on** 20 part(s) in 10 model(s): special effects (6), power-ups (perks) (4)
- **Parts**: `defaultelement`
- **For example** `destructionmodecolumn_orange.model`, `destructionmodecolumn_green.model`, `destructionmodecolumn_red.model`, `splitscreencolumn_bottomleft.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `mine_pulse_06` |
| `g_vColour` | number × 4 | 1, 0.625, 0.25, 0.3 |
| `g_vColourFresnel` | number × 4 | 0.5, 0.3125, 0.125, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game |  |
| `g_vScrollTextureY` | set by the game |  |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_DistanteFadeParams` | number × 4 | 100, 60, 0, 0 |
| `g_2L_tTexture` | texture | `mine_pulse_06` |
| `g_2L_vColour` | number × 4 | 1, 0.625, 0.25, 0.3 |
| `g_2L_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureX` | set by the game |  |
| `g_2L_vScrollTextureY` | set by the game |  |
| `g_2L_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectDLayerCullNDepth

- **Used on** 6 part(s) in 3 model(s): power-ups (perks) (3)
- **Parts**: `e_nitro_1_2`
- **For example** `nitrolevel2.model`, `nitro_carver.model`, `nitrolevel2nr.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `light_lines_02`, `light_paint_07` |
| `g_vColour` | set by the game |  |
| `g_vColourFresnel` | number × 4 | 0.20252, 0.323, 0.21055, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game |  |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_tTexture` | texture | `light_lines_04`, `light_paint_05` |
| `g_2L_vColour` | set by the game |  |
| `g_2L_vColourFresnel` | number × 4 | 0.20252, 0.323, 0.21055, 0 |
| `g_2L_vScrollTextureX` | set by the game |  |
| `g_2L_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectDLayerUVDist

- **Used on** 1 part(s) in 1 model(s): power-ups (perks) (1)
- **Parts**: `e_distortl`
- **For example** `bargewave1.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_2L_UvDistort` | number × 4 | 0.5, 0, 0, 0 |
| `g_tTexture` | texture | `lightning_01` |
| `g_vColour` | set by the game |  |
| `g_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vScrollTextureY` | set by the game |  |
| `g_2L_tUVDistortTexture` | texture | `uv_distort_faint` |
| `gUvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | number × 4 | 0, 0, 0, 0 |
| `gUvScrollDistortOffsetY` | number × 4 | 0, 0, 0, 0 |
| `gUvDistort` | number × 4 | 0.5, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort_faint` |
| `g_2L_tTexture` | texture | `lightning_01` |
| `g_2L_vColour` | set by the game |  |
| `g_2L_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureY` | set by the game |  |
| `g_2L_UvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectDLayerUVDistCull

- **Used on** 70 part(s) in 37 model(s): power-ups (perks) (37)
- **Parts**: `defaultelement`, `e_barge_build_pt2_03`, `e_psphere3`, `e_psphere4`
- **For example** `shieldedbaybubble.model`, `minecore2.model`, `repairpickupdecoyhit.model`, `roadsweeper_bolt_rotate.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_2L_UvDistort` | number × 4 | 1, 0, 0, 0 |
| `g_tTexture` | texture | `lightning_04`, `mine_pulse_03`, `lightning_02`, `lightning_01` |
| `g_vColour` | set by the game | 1, 0.58286, 0.417, 4 |
| `g_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_vScrollTextureY` | set by the game | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_tUVDistortTexture` | texture | `uv_distort_faint`, `DefaultColour`, `uv_distort` |
| `gUvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | set by the game | 0, 0, 0, 0 |
| `gUvScrollDistortOffsetY` | set by the game | 0, 0, 0, 0 |
| `gUvDistort` | number × 4 | 1, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort_faint`, `uv_distort` |
| `g_2L_tTexture` | texture | `lightning_01`, `DefaultColour`, `uv_distort_04`, `lightning_03` |
| `g_2L_vColour` | set by the game | 0, 0, 0, 0 |
| `g_2L_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetY` | set by the game | 0, 0, 0, 0 |

### MeshEffectDLayerUVDistCullNDepth

- **Used on** 8 part(s) in 3 model(s): power-ups (perks) (3)
- **Parts**: `e_shock_1_ball`, `e_innerdome`, `e_innerdome1`, `defaultelement`
- **For example** `shocklevel2.model`, `shocklevel2player.model`, `minedtcore1.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_2L_UvDistort` | number × 4 | 0.5, 0, 0, 0 |
| `g_tTexture` | texture | `lightning_02`, `mine_pulse_04`, `lightning_01` |
| `g_vColour` | set by the game | -1, -1, -1, 0.5 |
| `g_vColourFresnel` | number × 4 | 0.11901, 0.17851, 0.29752, 0 |
| `g_vFresnelPower` | set by the game | 0.5, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game |  |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_tUVDistortTexture` | texture | `uv_distort`, `uv_distort_02` |
| `gUvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetY` | set by the game | 0, 0, 0, 0 |
| `gUvDistort` | number × 4 | 1, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort` |
| `g_2L_tTexture` | texture | `lightning_02`, `mine_pulse_04`, `lightning_01` |
| `g_2L_vColour` | set by the game | 1, 0.53699, 0.311, 4 |
| `g_2L_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureY` | set by the game | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortScale` | number × 4 | 0.5, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectDLayerUVDistNDepth

- **Used on** 6 part(s) in 1 model(s): power-ups (perks) (1)
- **Parts**: `e_pplane1`, `e_pplane6`, `e_pplane5`, `e_pplane4`, `e_pplane3`, `e_pplane2`
- **For example** `shunt_flow_car_01.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_2L_UvDistort` | number × 4 | 0, 0, 0, 0 |
| `g_tTexture` | texture | `lightning_bolts_02` |
| `g_vColour` | set by the game |  |
| `g_vColourFresnel` | set by the game |  |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game |  |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_tUVDistortTexture` | texture | `DefaultColour` |
| `gUvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | set by the game |  |
| `gUvScrollDistortOffsetY` | set by the game |  |
| `gUvDistort` | number × 4 | 0.1, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort` |
| `g_2L_tTexture` | texture | `DefaultColour` |
| `g_2L_vColour` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortScale` | number × 4 | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetX` | number × 4 | 0, 0, 0, 0 |
| `g_2L_UvScrollDistortOffsetY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectNoDepth

- **Used on** 65 part(s) in 7 model(s): power-ups (perks) (7)
- **Parts**: `e_pplane1`, `e_pplane5`, `e_pplane4`, `e_pplane3`, `e_pplane2`, `e_pplane7`, `e_pplane6`, `e_lightningbolts2`, `defaultelement`
- **For example** `shuntpow1.model`, `blindfireshotgunpow.model`, `blindfire_pow_01.model`, `shocksparks02.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `lightning_bolts_06`, `lightning_bolts_02`, `lightning_bolts_04`, `mine_pulse_04` |
| `g_vColour` | set by the game | 0.25, 0.36462, 1, 2 |
| `g_vColourFresnel` | set by the game | 0, 0.26667, 0.8, 0 |
| `g_vFresnelPower` | number × 4 | 0.5, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game |  |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |

### MeshEffectRefract

- **Used on** 40 part(s) in 21 model(s): power-ups (perks) (21)
- **Parts**: `e_surface`, `e_torus`, `e_psphere2`, `e_inner`, `e_powerring`, `e_bumpershield`, `e_bumpersupershield`, `e_pcylinder1`, `e_distortl`, `e_distortr`
- **For example** `shieldlevel1.model`, `shieldsuper.model`, `mineblastimplode.model`, `nitroreversebumper01.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `lightning_03`, `lightning_grid_01`, `uv_distort`, `light_paint_02` |
| `g_vColour` | set by the game | 1, 1, 1, 0 |
| `g_vColourFresnel` | set by the game | 0, 0, 0, 0 |
| `g_vFresnelPower` | set by the game | 10, 0, 0, 0 |
| `g_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vScrollTextureY` | set by the game | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_pRefractionIntensity` | set by the game |  |
| `g_vRefractColour` | set by the game | 1, 1, 1, 1 |
| `g_vRefractColourFresnel` | set by the game | 1, 1, 1, 0 |

### MeshEffectUVDistort

- **Used on** 188 part(s) in 88 model(s): power-ups (perks) (61), special effects (27)
- **Parts**: `defaultelement`, `e_psphere1`, `e_pplane1`, `e_ball`, `e_outer`, `e_shock_up_pilllar_01`, `e_psphere2`, `e_shock_pickup`, `e_shock_sparks_02_pplane5`, `e_shock_sparks_02_pplane4`
- **For example** `shuntlevel1.model`, `bargelevel1.model`, `barged1env.model`, `shockfireup1.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `lightning_01`, `lightning_bolts_04`, `mine_pulse_02`, `lightning_02` |
| `g_vColour` | number × 4 | 1, 1, 0.3, 0.2 |
| `g_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `gUvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | set by the game | 0, 0, 0, 0 |
| `gUvScrollDistortOffsetY` | set by the game | 0, 0, 0, 0 |
| `gUvDistort` | number × 4 | 0.1, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort`, `uv_distort_03`, `uv_distort_faint`, `uv_distort_05` |

### MeshEffectUVDistortCull

- **Used on** 48 part(s) in 21 model(s): power-ups (perks) (21)
- **Parts**: `defaultelement`, `e_shock_1_ball`, `e_shock_1_ball2`, `e_shock_1_ball1`, `e_psphere2`, `e_ring`
- **For example** `mineboomcircles.model`, `mastermineboomcircles.model`, `roadsweeper_shock_norotate.model`, `roadsweeper_nitro_norotate.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `mine_pulse_03`, `lightning_01`, `lightning_03`, `mine_pulse_01` |
| `g_vColour` | set by the game |  |
| `g_vColourFresnel` | number × 4 | 0, 0, 0, 0 |
| `g_vFresnelPower` | number × 4 | 0.47934, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `gUvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | number × 4 | 0, 0, 0, 0 |
| `gUvScrollDistortOffsetY` | number × 4 | 0, 0, 0, 0 |
| `gUvDistort` | number × 4 | 0.25, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort_faint`, `uv_distort_04` |

### MeshEffectUVDistortCullNoDepth

- **Used on** 215 part(s) in 38 model(s): power-ups (perks) (38)
- **Parts**: `e_pplane7`, `e_pplane6`, `e_pplane5`, `e_pplane4`, `e_pplane3`, `e_pplane2`, `e_pplane1`, `e_imprint`, `e_psphere2`, `e_shunt_ball_core`
- **For example** `repairpickupdecoyhit.model`, `nitropickupdecoyhit.model`, `shieldpickupdecoyhit.model`, `shuntedball1.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `lightning_bolts_08`, `lightning_03`, `mine_pulse_06`, `light_lines_08` |
| `g_vColour` | set by the game | -0.7, -0.7, -0.7, 4 |
| `g_vColourFresnel` | set by the game | 0, 0, 0, 0 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `gUvScrollDistortScale` | number × 4 | 0.5, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | set by the game | 0, 0, 0, 0 |
| `gUvScrollDistortOffsetY` | set by the game | 0, 0, 0, 0 |
| `gUvDistort` | number × 4 | 0.25, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort`, `uv_distort_faint`, `mine_pulse_distort_01`, `mine_pulse_02` |

### MeshEffectUVDistortNoDepth

- **Used on** 73 part(s) in 16 model(s): power-ups (perks) (16)
- **Parts**: `e_sparkles`, `e_pcube3`, `e_ring9`, `e_ring7`, `e_ring6`, `e_ring5`, `e_ring4`, `e_ring3`, `e_ring2`, `e_ring1`
- **For example** `minecore1.model`, `masterminecore1.model`, `rifted.model`, `shuntprojectile1.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tTexture` | texture | `light_lines_08`, `lightning_bolts_04`, `lightning_bolts_08`, `shunt_pulse_01` |
| `g_vColour` | set by the game | 0.25, 0.36462, 1, 2 |
| `g_vColourFresnel` | number × 4 | 1, 0.26667, 0, 2 |
| `g_vFresnelPower` | number × 4 | 1, 0, 0, 0 |
| `g_vScrollTextureX` | set by the game | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vSpeedScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `gUvScrollDistortScale` | number × 4 | 1, 0, 0, 0 |
| `gUvScrollDistortOffsetX` | number × 4 | 0, 0, 0, 0 |
| `gUvScrollDistortOffsetY` | number × 4 | 0, 0, 0, 0 |
| `gUvDistort` | number × 4 | 1, 0, 0, 0 |
| `g_tUVDistortTexture` | texture | `uv_distort_faint`, `uv_distort`, `uv_distort_03`, `uv_mine_pulse_01` |

### Ocean_NL

- **Used on** 1 part(s) in 1 model(s): special effects (1)
- **Parts**: `e_water`
- **For example** `water_jet.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_fWaterSpecularIntensity` | number × 4 | 1, 0, 0, 0 |
| `g_tNormal` | texture | `water_jet_norm` |
| `g_vWaterColour` | number × 4 | 0, 0, 0, 0 |
| `g_vNormalScale0` | number × 4 | 1, 1, 0, 0 |
| `g_vNormalScale1` | number × 4 | 1, 1, 0, 0 |
| `g_vNormalVelocity0` | number × 4 | 0.01, 0.01, 0, 0 |
| `g_vNormalVelocity1` | number × 4 | 0.01, 0, 0, 0 |
| `g_tBlendNormal` | texture | `DefaultColour` |

### Puddle_NL_NV

- **Used on** 1 part(s) in 1 model(s): objects: usa_la_river (1)
- **Parts**: `defaultelement`
- **For example** `dynamicpuddlelevel.model`
- **Vertex data**: position, normal, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vNormalVelocity1` | number × 4 | 0.001, 0.01, 0, 0 |
| `g_tAlbedo` | texture | `puddle_alpha_diff` |
| `g_tBlendNormal` | texture | `puddle_alpha_norm` |
| `g_tMaterial` | texture | `puddle_alpha_ipr0` |
| `g_tNormal` | texture | `puddle_alpha_norm` |
| `g_vWaterColour` | number × 4 | 0.275, 0.263, 0.08993, 0.7 |
| `g_fRippleIntensity` | number × 4 | 0.1, 0, 0, 0 |
| `g_vNormalScale0` | number × 4 | 2, 1, 0, 0 |
| `g_vNormalScale1` | number × 4 | 2, 1, 0, 0 |
| `g_vNormalVelocity0` | number × 4 | 0.01, 0.001, 0, 0 |

### ScreenFacingSprite

- **Used on** 3 part(s) in 2 model(s): special effects (2)
- **Parts**: `defaultelement`, `e_tumbleweed`
- **For example** `lantern01.model`, `tumbleweed.model`
- **Vertex data**: position, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `lantern01_diff`, `sprig_diff` |

### ScrollFade_NL

- **Used on** 98 part(s) in 5 model(s): special effects (5)
- **Parts**: `defaultelement`, `e_hydrantspray`
- **For example** `brighton_tide1.model`, `saus_tide1.model`, `brightonmultiplayer_tide1.model`, `hydrantspray.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `tide_02`, `tide_01`, `hydrantspray`, `jettrail` |
| `g_tMaterial` | texture | `DefaultColour` |
| `g_fScrollX` | set by the game | 0, 0, 0, 0 |
| `g_fScrollY` | number × 4 | 0, 0, 0, 0 |
| `g_fScrollSpeedX` | number × 4 | 0, 0, 0, 0 |
| `g_fScrollSpeedY` | number × 4 | 0, 0, 0, 0 |

### ScrollFade_skin_NL

- **Used on** 1 part(s) in 1 model(s): special effects (1)
- **Parts**: `e_electricity`
- **For example** `electricity01.model`
- **Vertex data**: position, normal, UV, bone numbers, bone weights, colour (skinned)

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tAlbedo` | texture | `electricity_diff` |
| `g_tMaterial` | texture | `electricity_ipr0` |
| `g_fScrollSpeedY` | number × 4 | 0, 0, 0, 0 |
| `g_fScrollX` | number × 4 | 0, 0, 0, 0 |
| `g_fScrollY` | set by the game |  |
| `g_fScrollSpeedX` | number × 4 | 0, 0, 0, 0 |

Also a pass with `g_mPalette` (set by the game).

### ScrollUVNeon_NV

- **Used on** 1 part(s) in 1 model(s): objects: usa_amboy (1)
- **Parts**: `defaultelement`
- **For example** `spline_plane.model`
- **Vertex data**: position, normal, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tNeon` | texture | `DefaultColour` |
| `g_tAlbedo` | texture | `propeller_diff` |
| `g_tMaterial` | texture | `DefaultColour` |
| `g_vScrollTextureX` | number × 4 | 0, 0, 0, 0 |
| `g_vScrollTextureY` | number × 4 | 0, 0, 0, 0 |
| `g_vScrollSpeedX` | number × 4 | 5, 0, 0, 0 |
| `g_vScrollSpeedY` | number × 4 | 0, 0, 0, 0 |

Also a pass with `g_tLightmap` (set by the game).

### SoftLightFlare

- **Used on** 5 part(s) in 3 model(s): special effects (2), objects: shared (1)
- **Parts**: `defaultelement`
- **For example** `light_projection_beam.model`, `helilight.model`, `traffic_cone01_light.model`
- **Vertex data**: position, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_tColour` | texture | `lightflare_ring_diff`, `lightflare_diff` |
| `g_vLightFlareColour` | number × 4 | 1, 1, 1, 0 |
| `g_fLightFlareIntensity` | number × 4 | 1, 0, 0, 0 |
| `g_fLightFlareSize` | number × 4 | 1, 0, 0, 0 |

### veh_Alloy_a_b_f

- **Used on** 364 part(s) in 127 model(s): vehicles (73), wheels (54)
- **Parts**: `e_alloyrim_backleft`, `e_alloyrim_frontleft`, `defaultelement`, `e_alloyrim_frontright`, `e_alloyrim_backright`, `e_exterior`, `e_gearstick`, `e_interior`, `e_wing_right`, `e_boot`
- **For example** `volkswagen_golfw12650_stock.model`, `foose_69_stock.model`, `dodge_challenger_tuner.model`, `bmw_m3e92_drift.model`
- **Vertex data**: position, normal, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0.1, 0.01, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 1, 1, 1, 1 |

Also a pass with `g_LocalSpaceSHNode` (set by the game).

### veh_Alloy_a_f

- **Used on** 3 part(s) in 3 model(s): wheels (3)
- **Parts**: `defaultelement`
- **For example** `audi_tt_stock.model`, `dodge_challenger_stock.model`, `audi_r8v10_stock.model`
- **Vertex data**: position, normal, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_BumpTexture` | texture | `alloy_cap`, `wheelbadge`, `bump` |
| `g_vMtlParameters` | number × 8 | 0.1, 0.01, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 1, 1, 1, 1 |

Also a pass with `g_LocalSpaceSHNode` (set by the game).

### veh_Alloy_b_f

- **Used on** 107 part(s) in 63 model(s): wheels (55), vehicles (8)
- **Parts**: `m_alloy`, `defaultelement`, `e_alloyrim_backleft`, `e_alloyrim_frontleft`, `e_alloyrim_frontright`, `e_alloyrim_backright`, `e_exterior`, `e_brakecaliper_frontleft`, `e_brakecaliper_frontright`, `e_brakecaliper_backleft`
- **For example** `nissan_navara_offroad.model`, `nissan_skyliner34ztune_stock.model`, `ford_supervan_stock.model`, `nissan_navara_rat.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `blur`, `nismo_1`, `navara_offroad_2`, `fordgt_general_texture_a` |
| `g_vMtlParameters` | number × 8 | 0.1, 0.01, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 1, 1, 1, 1 |

Also a pass with `g_LocalSpaceSHNode` (set by the game).

### veh_Alloy_f

- **Used on** 5 part(s) in 4 model(s): wheels (4)
- **Parts**: `defaultelement`
- **For example** `corvette_zr1_stock.model`, `dodge_viperacr_stock.model`, `foose_stallion.model`, `hennessey_vipervenom1000coupe_stock.model`
- **Vertex data**: position, normal, UV, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_BumpTexture` | texture | `texture 2`, `dodge_viper_wheel`, `gt500_wheel`, `dodge_viper_h_wheel` |
| `g_vMtlParameters` | number × 8 | 0.1, 0.01, 1, 1, 0.497, 0.497, 0.497, 0 |
| `g_MattParams` | number × 4 | 0, 0, 0, 1 |
| `g_MeshTexture` | texture | `corvette_zr1_wheel`, `dodge_viper_wheel`, `blur`, `dodge_viper_h_wheel` |

Also a pass with `g_LocalSpaceSHNode` (set by the game).

### veh_Alpha

- **Used on** 29 part(s) in 16 model(s): vehicles (16)
- **Parts**: `e_bumper_front`, `e_bonnet`, `e_bumper_back`, `e_wing_right`, `e_wing_left`, `e_boot`
- **For example** `dodge_challenger_legend_v.model`, `dodge_challenger_stock.model`, `ford_mustanggtr_legend_x.model`, `hennessey_vipervenom1000coupe_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `dodge_decals`, `ford_mustang_gtr_alpha`, `corvette_zr1_lights`, `dodge_viper_decals` |
| `g_vMtlParameters` | number × 8 | 0.11, 0.626, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Alpha_c

- **Used on** 38 part(s) in 25 model(s): vehicles (25)
- **Parts**: `e_exterior`, `e_boot`, `e_door_right`, `e_door_left`, `e_bumper_back`, `e_wing_frontright`, `e_wing_frontleft`, `e_bumper_front`, `e_headlightcover_right`, `e_headlightcover_left`
- **For example** `landrover_defendersvx_stock.model`, `dodge_challenger_legend_v.model`, `renault_meganetrophy_stock.model`, `dodge_challenger_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `dodge_decals`, `ford_mustang_gtr_alpha`, `svx_alpha`, `trophy_alpha` |
| `g_vMtlParameters` | number × 8 | 0.11, 0.626, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Alpha_c_h

- **Used on** 23 part(s) in 16 model(s): vehicles (16)
- **Parts**: `e_exterior`, `e_interior`, `e_steeringwheel`, `e_wing_frontleft`, `e_wing_frontright`, `e_door_left`
- **For example** `chevrolet_camaro_stock.model`, `ford_mustanggtr_legend_x.model`, `ford_mustanggtr_stock.model`, `ford_fr100_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `ford_mustang_gtr_alpha`, `camaro_alpha`, `dodge_decals`, `fordf100_alpha` |
| `g_vMtlParameters` | number × 8 | 0.11, 0.626, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_b

- **Used on** 20 part(s) in 7 model(s): vehicles (7)
- **Parts**: `e_bumper_back`, `e_wing_left`, `e_wing_right`, `e_bumper_front`, `e_bonnet`, `e_boot`
- **For example** `dodge_challenger_race.model`, `renault_meganesportr26_stock_shannon.model`, `hummer_h2_offroad.model`, `hummer_h2_offroad_drayke.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `r26-scratch`, `hummer_scratch`, `dodge_racer_scratch`, `broncoscratch_1` |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0.032, 0.032, 0.032, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_b_c

- **Used on** 53 part(s) in 16 model(s): vehicles (16)
- **Parts**: `e_exterior`, `e_door_right`, `e_door_left`, `e_mirror_left`, `e_mirror_right`, `e_boot`, `e_door_frontright`, `e_wing_frontleft`, `e_wing_frontright`, `e_door_frontleft`
- **For example** `renault_meganesportr26_stock_shannon.model`, `renault_meganesportr26_stock.model`, `foose_69_stock.model`, `lotus_exigecup260_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `r26-scratch`, `camaro_foose_scratch`, `gt500_scratch`, `lotus_260_scratch` |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0.032, 0.032, 0.032, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_b_c_f

- **Used on** 590 part(s) in 76 model(s): vehicles (76)
- **Parts**: `e_exterior`, `e_door_right`, `e_mirror_left`, `e_mirror_right`, `e_door_left`, `e_boot`, `e_wing_frontleft`, `e_wing_frontright`, `e_bumper_back`, `e_bumper_front`
- **For example** `nissan_350z_drift.model`, `hummer_h2_offroad.model`, `hummer_h2_offroad_drayke.model`, `volkswagen_beetle_rat.model`
- **Vertex data**: position, normal, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Default_a_b_c_f_h

- **Used on** 912 part(s) in 75 model(s): vehicles (75)
- **Parts**: `e_exterior`, `e_interior`, `e_mirror_centre`, `e_steeringwheel`, `e_brakecaliper_backright`, `e_brakecaliper_frontright`, `e_brakecaliper_backleft`, `e_brakecaliper_frontleft`, `e_brakedisc_frontright`, `e_brakedisc_backright`
- **For example** `nissan_350znismo_stock.model`, `landrover_lrx_stock.model`, `bmw_1seriestii_stock.model`, `chevrolet_camaross_stock_rymer.model`
- **Vertex data**: position, normal, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Default_a_b_c_h

- **Used on** 77 part(s) in 13 model(s): vehicles (13)
- **Parts**: `e_exterior`, `e_interior`, `e_brakecaliper_frontleft`, `e_brakecaliper_backright`, `e_brakecaliper_backleft`, `e_brakecaliper_frontright`, `e_steeringwheel`, `e_wiper_left`, `e_wiper_right`, `e_wiper_frontright`
- **For example** `foose_69_stock.model`, `chevrolet_camaro_stock.model`, `renault_meganesportr26_stock_shannon.model`, `renault_meganesportr26_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `r26-scratch`, `camaro_foose_scratch`, `camaro_scratch`, `dodge_racer_scratch` |
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0.103, 0.103, 0.103, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_b_f

- **Used on** 217 part(s) in 52 model(s): vehicles (52)
- **Parts**: `e_bumper_front`, `e_bonnet`, `e_bumper_back`, `e_wing_left`, `e_wing_right`, `e_boot`, `e_wing_frontleft`, `e_wing_frontright`
- **For example** `landrover_lrx_stock.model`, `chevrolet_camaross_stock_rymer.model`, `chevrolet_camaro_legend_ii.model`, `chevrolet_camaross_stock.model`
- **Vertex data**: position, normal, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0, 0, 0, 0, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Default_a_b_f_h

- **Used on** 4 part(s) in 2 model(s): vehicles (2)
- **Parts**: `e_bumper_back`, `e_wing_right`, `e_wing_left`
- **For example** `hummer_h2_rat.model`, `ford_focusrs_stock.model`
- **Vertex data**: position, normal, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0.032, 0.065, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Default_a_b_h

- **Used on** 3 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_wing_left`, `e_wing_right`, `e_bumper_back`
- **For example** `hummer_h2_rat.model`
- **Vertex data**: position, normal, UV, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `hummer_rat_scratch` |
| `g_vMtlParameters` | number × 8 | 0.032, 0.065, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_c

- **Used on** 4 part(s) in 2 model(s): vehicles (2)
- **Parts**: `e_door_frontright`, `e_door_frontleft`
- **For example** `renault_meganesportr26_stock_shannon.model`, `renault_meganesportr26_stock.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `r26-scratch` |
| `g_vMtlParameters` | number × 8 | 1, 1, 1, 1, 0, 0, 0, 0 |
| `g_BumpTexture` | texture | `r26-bump` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_c_f

- **Used on** 5 part(s) in 5 model(s): vehicles (5)
- **Parts**: `e_boot`, `e_exterior`
- **For example** `audi_r8v10_stock.model`, `nissan_skyliner34ztune_stock_harumi.model`, `nissan_skyliner34ztune_stock.model`, `volkswagen_beetle_rat.model`
- **Vertex data**: position, normal, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_BumpTexture` | texture | `nismo_bump`, `audir8_1`, `texture_beetle_51` |
| `g_vMtlParameters` | number × 8 | 1, 1, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_c_f_h

- **Used on** 9 part(s) in 6 model(s): vehicles (6)
- **Parts**: `e_exterior`, `e_bumper_back`
- **For example** `nissan_skyliner34ztune_stock_harumi.model`, `nissan_skyliner34ztune_stock.model`, `nissan_skyliner34ztune_stock_ayumi.model`, `volkswagen_beetle_rat.model`
- **Vertex data**: position, normal, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_BumpTexture` | texture | `nismo_bump`, `texture_beetle_51`, `focusrs-text01`, `focusrsrace-text01` |
| `g_vMtlParameters` | number × 8 | 1, 1, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_a_c_h

- **Used on** 6 part(s) in 2 model(s): vehicles (2)
- **Parts**: `e_rearlight_left`, `e_rearlight_right`, `e_exterior`
- **For example** `renault_meganesportr26_stock_shannon.model`, `renault_meganesportr26_stock.model`
- **Vertex data**: position, normal, UV, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `r26-scratch` |
| `g_vMtlParameters` | number × 8 | 1, 1, 1, 1, 0, 0, 0, 0 |
| `g_BumpTexture` | texture | `r26-bump` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_b

- **Used on** 8 part(s) in 7 model(s): vehicles (7)
- **Parts**: `e_bonnet`, `e_bumper_front`
- **For example** `volkswagen_golfw12650_stock.model`, `bmw_1seriestii_race_natalya.model`, `audi_s3_stock.model`, `hummer_h2_offroad.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `bmw_tii_race_scratch`, `w12_interior`, `hummer_scratch`, `smashedglass` |
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `bmw_tii_race_text1`, `w12_interior`, `hummer_1`, `audis3_alpha` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_b_c

- **Used on** 12 part(s) in 4 model(s): vehicles (4)
- **Parts**: `e_exterior`, `e_door_left`, `e_door_right`, `e_wing_right`, `e_wing_left`, `e_bumper_back`, `e_boot`
- **For example** `volkswagen_golfw12650_stock.model`, `lotus_exigecup260_stock.model`, `ford_bronco_offroad.model`, `landrover_defendersvx_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `w12_interior`, `lotus_260_scratch`, `broncoscratch_1`, `svx_scratches` |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `w12_interior`, `lotus_260_interior`, `broncotex_1`, `svx_2` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_b_c_f

- **Used on** 483 part(s) in 74 model(s): vehicles (74)
- **Parts**: `e_exterior`, `e_door_right`, `e_door_left`, `e_boot`, `e_mirror_left`, `e_mirror_right`, `e_door_frontleft`, `e_wing_frontleft`, `e_wing_frontright`, `e_door_frontright`
- **For example** `opel_astraextreme_stock_shannon.model`, `opel_astraextreme_stock.model`, `opel_astra_extreme_legend_viii.model`, `ford_supervan_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `nismo_1`, `carbonfibre`, `opelastraextreme_1`, `opelastraextreme_2` |
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_b_c_f_h

- **Used on** 1119 part(s) in 80 model(s): vehicles (80)
- **Parts**: `e_exterior`, `e_interior`, `e_brakedisc_frontright`, `e_brakedisc_backright`, `e_brakedisc_backleft`, `e_brakedisc_frontleft`, `e_steeringwheel`, `e_brakecaliper_frontleft`, `e_brakecaliper_frontright`, `e_gearstick`
- **For example** `koenigsegg_ccxr_stock.model`, `ford_gt_stock.model`, `audi_tt_legend_vi.model`, `audi_tt_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `breakdisc`, `auditt-s_1`, `r26-detail`, `ford_mustang_gtr_interior` |
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_b_c_h

- **Used on** 19 part(s) in 2 model(s): vehicles (2)
- **Parts**: `e_interior`, `e_gearstick`, `e_steering_wheel`, `e_steeringwheel`, `e_mirror_centre`, `e_rearlight_right`, `e_rearlight_left`, `e_door_left`, `e_exterior`, `e_brakecaliper_frontright`
- **For example** `lotus_exigecup260_stock.model`, `volkswagen_golfw12650_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `lotus_260_scratch`, `w12_interior` |
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `lotus_260_interior`, `w12_interior`, `lotus_260_decals` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_b_f

- **Used on** 247 part(s) in 68 model(s): vehicles (68)
- **Parts**: `e_bumper_front`, `e_bonnet`, `e_bumper_back`, `e_wing_left`, `e_wing_right`, `e_boot`, `e_wing_frontleft`, `e_wing_frontright`
- **For example** `ford_gt_stock.model`, `chevrolet_socalhhr_stock.model`, `audi_s3_stock.model`, `dodge_viperacr_legend_iii.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `dodge_viper_lights`, `opelastraextreme_2`, `gt500_2`, `dodge_viper_gts-r_lights` |
| `g_vMtlParameters` | number × 8 | 0.05, 0.35, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_b_f_h

- **Used on** 2 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_bumper_front`
- **For example** `ford_f150_offroad.model`
- **Vertex data**: position, normal, UV, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `f150offroad-text2`, `f150offroad-alpha` |
| `g_vMtlParameters` | number × 8 | 0.1, 0.01, 1, 1, 0.247, 0.231, 0.176, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_c

- **Used on** 1 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_exterior`
- **For example** `volkswagen_golfw12650_stock.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `w12_interior` |
| `g_vMtlParameters` | number × 8 | 0.004, 0, 4, 1, 1, 0, 0, 0 |
| `g_BumpTexture` | texture | `texture 9` |
| `g_MeshTexture` | texture | `w12_interior` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_c_f

- **Used on** 25 part(s) in 25 model(s): vehicles (25)
- **Parts**: `e_exterior`, `e_boot`, `e_bonnet`
- **For example** `chevrolet_camaro_stock.model`, `chevrolet_camaross_stock_rymer.model`, `bmw_1seriestii_race_natalya.model`, `shelby_mustanggt500_stock.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_BumpTexture` | texture | `texture 8`, `underside_nrm`, `texture 7`, `underside_smallnmr` |
| `g_vMtlParameters` | number × 8 | 0, 0, 4, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `chevrolet_camaro_2`, `nismo_1`, `bmw_tii_race_text1`, `dodge_viper_gts-r_decals` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_c_f_h

- **Used on** 76 part(s) in 22 model(s): vehicles (22)
- **Parts**: `e_tyre_frontright`, `e_tyre_frontleft`, `e_tyre_backleft`, `e_tyre_backright`, `e_exterior`, `e_brakecaliper_backright`, `e_brakecaliper_backleft`, `e_brakecaliper_frontleft`, `e_brakecaliper_frontright`, `e_bumper_front`
- **For example** `toyota_supratrd_stock.model`, `toyota_supra_smooth.model`, `dodge_challenger_legend_v.model`, `dodge_challenger_stock.model`
- **Vertex data**: position, normal, UV, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_BumpTexture` | texture | `tyretred_bump_nrm`, `tyrewall_nrm`, `dodge_nrm`, `gt500_2` |
| `g_vMtlParameters` | number × 8 | 0, 0, 5, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `tyretred`, `tyrewall`, `dodge_interior`, `gt500_2` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Default_f

- **Used on** 7 part(s) in 7 model(s): vehicles (7)
- **Parts**: `e_bumper_front`, `e_bonnet`
- **For example** `chevrolet_camaross_stock_rymer.model`, `shelby_mustanggt500_stock.model`, `chevrolet_camaro_legend_ii.model`, `dodge_challenger_legend_v.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_BumpTexture` | texture | `texture 10`, `dodge_lights`, `gt500_1`, `texture_beetle_51` |
| `g_vMtlParameters` | number × 8 | 0.004, 0.067, 1, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `chevrolet_camaro_2`, `dodge_lights`, `gt500_2`, `texture_beetle_51` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_a_c

- **Used on** 21 part(s) in 13 model(s): vehicles (13)
- **Parts**: `e_window_back`, `e_window_frontright`, `e_window_frontleft`, `e_window_rear`, `e_headlightcover_frontright`, `e_headlightcover_frontleft`
- **For example** `chevrolet_socalhhr_stock.model`, `volkswagen_golfw12650_stock.model`, `volkswagen_beetle_offroad.model`, `volkswagen_beetle_rat.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `smashedglass_nrm` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |
| `g_ScratchTexture` | texture | `smashedglass` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_a_c_d

- **Used on** 50 part(s) in 19 model(s): vehicles (19)
- **Parts**: `e_window_frontright`, `e_window_frontleft`, `e_headlightcover_frontleft`, `e_headlightcover_frontright`, `e_window_right`, `e_window_left`, `e_headlightcover_left`, `e_headlightcover_right`, `e_exterior`, `e_wing_left`
- **For example** `ford_f100_offroad.model`, `dodge_challenger_tuner.model`, `ford_f100_rat.model`, `dodge_challenger_legend_v.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `smashedglass` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_a_c_d_h

- **Used on** 196 part(s) in 48 model(s): vehicles (48)
- **Parts**: `e_window_frontright`, `e_window_frontleft`, `e_window_backright`, `e_headlightcover_frontright`, `e_headlightcover_frontleft`, `e_window_backleft`, `e_headlightcover_left`, `e_headlightcover_backleft`, `e_headlightcover_backright`, `e_headlightcover_right`
- **For example** `audi_r8v10_stock.model`, `audi_tt_legend_vi.model`, `audi_tt_stock.model`, `renault_meganesportr26_stock_shannon.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `smashedglass`, `DefaultColour` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_a_c_h

- **Used on** 123 part(s) in 40 model(s): vehicles (40)
- **Parts**: `e_window_front`, `e_window_back`, `e_window_backright`, `e_window_backleft`, `e_window_rear`, `e_headlightcover_frontright`, `e_headlightcover_frontleft`, `e_window_frontright`, `e_window_frontleft`, `e_window_left`
- **For example** `volkswagen_golfw12650_stock.model`, `nissan_navara_rat.model`, `ford_focusrs_race.model`, `corvette_zr1_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `smashedglass_nrm` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |
| `g_ScratchTexture` | texture | `smashedglass` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_c

- **Used on** 17 part(s) in 6 model(s): vehicles (6)
- **Parts**: `e_window_frontright`, `e_window_frontleft`, `e_window_rear`, `e_window_back`, `e_headlightcover_frontright`, `e_window_backleft`, `e_headlightcover_frontleft`, `e_window_backright`, `e_window_front`, `e_headlightcover_right`
- **For example** `toyota_supratrd_stock.model`, `ford_supervan_stock.model`, `chevrolet_camaross_drag.model`, `ford_gt_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `smashedglass_nrm` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |
| `g_ScratchTexture` | texture | `smashedglass` |
| `g_MeshTexture` | texture | `toy_supra_alpha`, `supervan_glass_plus`, `chevrolet_camaro_drag_alpha`, `fordgt_glass_plus` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_c_d

- **Used on** 30 part(s) in 10 model(s): vehicles (10)
- **Parts**: `e_window_frontright`, `e_window_frontleft`, `e_headlightcover_left`, `e_headlightcover_right`, `e_mirror_right`, `e_mirror_left`, `e_foglightcover_frontleft`, `e_foglightcover_frontright`, `e_headlightcover_frontleft`, `e_window_right`
- **For example** `ford_gt_stock.model`, `chevrolet_camaross_stock_rymer.model`, `chevrolet_camaro_legend_ii.model`, `chevrolet_camaross_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `smashedglass`, `DefaultColour` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `chevrolet_camaro_alpha`, `opelastraextreme_alpha`, `fordgt_glass_plus`, `bmw_ac_alpha` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_c_d_h

- **Used on** 86 part(s) in 23 model(s): vehicles (23)
- **Parts**: `e_window_backright`, `e_window_backleft`, `e_headlightcover_frontright`, `e_headlightcover_frontleft`, `e_window_frontright`, `e_window_frontleft`, `e_window_front`, `e_window_right`, `e_window_left`, `e_interior`
- **For example** `opel_astraextreme_stock_shannon.model`, `opel_astraextreme_stock.model`, `opel_astra_extreme_legend_viii.model`, `dodge_vipergtsr_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `smashedglass`, `DefaultColour` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `opelastraextreme_alpha`, `dodge_viper_gts-r_decals`, `bmw_ac_alpha`, `dodge_viper_decals` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_c_h

- **Used on** 106 part(s) in 39 model(s): vehicles (39)
- **Parts**: `e_window_front`, `e_window_back`, `e_window_backright`, `e_window_backleft`, `e_window_rear`, `e_window_frontright`, `e_window_frontleft`, `e_window_top`, `e_headlightcover_backleft`, `e_headlightcover_backright`
- **For example** `toyota_supra_smooth.model`, `koenigsegg_ccxr_stock.model`, `landrover_lrx_stock.model`, `volkswagen_scirocco_24.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `smashedglass_nrm` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |
| `g_ScratchTexture` | texture | `smashedglass` |
| `g_MeshTexture` | texture | `nismo_alpha`, `toyota_supra_smooth_alpha`, `ccxr_glass_areas`, `land_rover_lrx_alpha` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Glass_d

- **Used on** 1 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_bumper_front`
- **For example** `volkswagen_scirocco_24.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_ScratchTexture` | texture | `DefaultColour` |
| `g_vMtlParameters` | number × 8 | 0.5, 1, 1, 1, 0, 0, 0, 0 |
| `g_MeshTexture` | texture | `vwscirrocco24_alpha` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Light_c

- **Used on** 288 part(s) in 51 model(s): vehicles (51)
- **Parts**: `e_brakelight_centre`, `e_signallight_frontleft`, `e_signallight_frontright`, `e_foglight_frontleft`, `e_foglight_frontright`, `e_headlight_right`, `e_headlight_left`, `e_reverselight_left`, `e_runninglight_backright`, `e_runninglight_backleft`
- **For example** `ford_gt_stock.model`, `dodge_challenger_race.model`, `chevrolet_camaross_stock_rymer.model`, `chevrolet_camaro_legend_ii.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0.194, 1, 1, 1, 1, 0, 0, 0 |
| `g_sOffTexture` | texture | `chevrolet_camaro_2`, `dodge_lights`, `dodge_racer_lights_b`, `fordf100_2` |
| `g_sOnTexture` | texture | `chevrolet_camaro_2`, `dodge_lights`, `dodge_racer_lights_b`, `fordf100_2` |
| `g_sOffTextureDamage` | texture | `chevrolet_camaro_2`, `dodge_lights`, `dodge_racer_lights_b`, `fordf100_2` |
| `g_sOnTextureDamage` | texture | `chevrolet_camaro_2`, `dodge_lights`, `dodge_racer_lights_b`, `fordf100_2` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Light_c_h

- **Used on** 636 part(s) in 71 model(s): vehicles (71)
- **Parts**: `e_reverselight_right`, `e_reverselight_left`, `e_brakelight_left`, `e_rearlight_right`, `e_rearlight_left`, `e_brakelight_right`, `e_headlight_left`, `e_headlight_right`, `e_signallight_frontright`, `e_signallight_frontleft`
- **For example** `corvette_zr1_stock.model`, `corvette_zr1_stock_talon.model`, `renault_meganesportr26_stock_shannon.model`, `renault_meganesportr26_stock.model`
- **Vertex data**: position, normal, UV, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0.194, 1, 1, 1, 1, 0, 0, 0 |
| `g_sOffTexture` | texture | `dodge_viper_lights`, `corvette_zr1_lights`, `r26-detail`, `nismo_1` |
| `g_sOnTexture` | texture | `dodge_viper_lights`, `corvette_zr1_lights`, `r26-bump`, `nismo_1` |
| `g_sOffTextureDamage` | texture | `dodge_viper_lights`, `corvette_zr1_lights`, `r26-bump`, `nismo_1` |
| `g_sOnTextureDamage` | texture | `dodge_viper_lights`, `corvette_zr1_lights`, `r26-bump`, `nismo_1` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Matt_a_b_c_f

- **Used on** 25 part(s) in 3 model(s): vehicles (3)
- **Parts**: `e_exterior`, `e_door_left`, `e_door_right`, `e_mirror_right`, `e_mirror_left`, `e_wing_frontleft`, `e_wing_frontright`
- **For example** `ford_f150_offroad.model`, `shelby_mustanggt500_stock.model`, `ford_focusrs_race.model`
- **Vertex data**: position, normal, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_a_b_c_f_h

- **Used on** 29 part(s) in 4 model(s): vehicles (4)
- **Parts**: `e_exterior`, `e_wiper_left`, `e_wiper_right`, `e_brakecaliper_frontleft`, `e_brakecaliper_backleft`, `e_brakecaliper_backright`, `e_brakecaliper_frontright`, `e_interior`, `e_headlight_frontright`, `e_mirror_center`
- **For example** `ford_focusrs_race.model`, `ford_f150_offroad.model`, `shelby_mustanggt500_stock.model`, `volkswagen_beetle_rat.model`
- **Vertex data**: position, normal, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_a_b_f

- **Used on** 19 part(s) in 8 model(s): vehicles (8)
- **Parts**: `e_bonnet`, `e_bumper_front`, `e_bumper_back`, `e_wing_frontleft`, `e_wing_frontright`, `e_boot`
- **For example** `ford_focusrs_race.model`, `shelby_mustanggt500_stock.model`, `foose_stallion_stock_khan.model`, `ford_f150_offroad.model`
- **Vertex data**: position, normal, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_a_b_f_h

- **Used on** 3 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_bumper_front`
- **For example** `ford_f150_offroad.model`
- **Vertex data**: position, normal, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |
| `g_vMtlParameters` | number × 8 | 0.1, 0.01, 1, 1, 0, 0, 0, 0 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_b

- **Used on** 1 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_bonnet`
- **For example** `bmw_1seriestii_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `bmw_tii_bonnet` |
| `g_ScratchTexture` | texture | `bmw_tii_scratch` |
| `g_vMtlParameters` | number × 8 | 0.1, 0.01, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Matt_b_c_f

- **Used on** 11 part(s) in 4 model(s): vehicles (4)
- **Parts**: `e_exterior`, `e_wing_frontright`, `e_door_left`, `e_door_right`, `e_wing_frontleft`, `e_boot`
- **For example** `ford_f150_offroad.model`, `lotus_exigecup260_stock.model`, `shelby_mustanggt500_stock.model`, `corvette_c3_drag.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `f150offroad-text1`, `lotus_260_lights`, `gt500_2`, `corvettedrag_dials` |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_b_c_f_h

- **Used on** 12 part(s) in 7 model(s): vehicles (7)
- **Parts**: `e_exterior`, `e_interior`, `e_exhaust`, `e_steeringwheel`, `e_signalstalk`, `e_mirror_center`
- **For example** `ford_f150_offroad.model`, `corvette_zr1_stock.model`, `foose_stallion_stock_khan.model`, `corvette_c3_drag.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `f150offroad-text1`, `corvette_zr1_interior`, `gt500_2`, `corvettedrag_dials` |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_b_f

- **Used on** 4 part(s) in 3 model(s): vehicles (3)
- **Parts**: `e_bumper_front`, `e_bonnet`, `e_bumper_back`
- **For example** `renault_meganetrophy_stock.model`, `corvette_c3_drag.model`, `ford_focusrs_race.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `trophy_2`, `corvettedrag_dials`, `focusrsrace-text01` |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_b_f_h

- **Used on** 1 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_bumper_front`
- **For example** `ford_f150_offroad.model`
- **Vertex data**: position, normal, UV, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `f150offroad-text1` |
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_vCodeDamageScale`, `g_LocalSpaceSHNode` (set by the game).

### veh_Matt_c_f

- **Used on** 45 part(s) in 33 model(s): vehicles (33)
- **Parts**: `e_exterior`, `e_boot`, `defaultelement`, `e_door_right`, `e_door_left`
- **For example** `toyota_supratrd_stock.model`, `nissan_navara_offroad.model`, `hummer_h2_offroad.model`, `ford_f150_offroad.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `tyrewall`, `underside_small`, `tyretred_offroad`, `underside` |
| `g_BumpTexture` | texture | `underside_nrm`, `tyrewall_nrm`, `tyretred_bump_nrm`, `undersidenrm` |
| `g_vMtlParameters` | number × 8 | 0, 0, 4, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Matt_c_f_h

- **Used on** 610 part(s) in 78 model(s): vehicles (78)
- **Parts**: `e_tyre_frontright`, `e_tyre_backleft`, `e_tyre_frontleft`, `e_tyre_backright`, `e_exterior`, `e_tyre_rearright`, `e_brakecaliper_backright`, `e_brakecaliper_frontright`, `e_brakecaliper_backleft`, `e_brakecaliper_frontleft`
- **For example** `bmw_1seriestii_race_natalya.model`, `bmw_1seriestii_race.model`, `ford_bronco_offroad.model`, `ford_f100_offroad.model`
- **Vertex data**: position, normal, UV, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `tyrewall`, `tyretred`, `tyretred_offroad`, `tyretred_race` |
| `g_BumpTexture` | texture | `tyrewall_nrm`, `tyretred_bump_nrm`, `tyretred_race_nrm`, `tyretred_offroad_nrm` |
| `g_vMtlParameters` | number × 8 | 0, 0, 5, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Matt_f

- **Used on** 4 part(s) in 4 model(s): vehicles (4)
- **Parts**: `e_bumper_front`, `e_bonnet`
- **For example** `koenigsegg_ccxr_stock.model`, `bmw_m3e92_drift.model`, `toyota_supratrd_stock.model`, `bmw_m3e92_legend_ix.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `m3drift_2`, `ccxr_underside`, `tyrewall` |
| `g_BumpTexture` | texture | `m3drift_underside_nrm`, `ccxr_underside_nrm`, `tyretred_bump_nrm` |
| `g_vMtlParameters` | number × 8 | 0, 0, 4, 1, 0, 0, 0, 0 |
| `g_MattParams` | number × 4 | 0.01, 0.01, 0.01, 1 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Neon_c

- **Used on** 2 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_mirror_right`, `e_mirror_left`
- **For example** `volkswagen_golfw12650_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DamageTexture` | texture | `w12_interior` |
| `g_vMtlParameters` | number × 8 | 0.194, 1, 1, 1, 1, 0, 0, 0 |
| `g_MeshTexture` | texture | `w12_lights` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Neon_c_g

- **Used on** 15 part(s) in 10 model(s): vehicles (10)
- **Parts**: `e_licenseplate_front`, `e_licenseplate_back`, `e_licenseplate_rear`
- **For example** `nissan_navara_offroad.model`, `ford_gt_stock.model`, `chevrolet_socalhhr_stock.model`, `bmw_x548msport_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `cali_14`, `nyc_04`, `cali_11`, `cali_01` |
| `g_vMtlParameters` | number × 8 | 0.194, 1, 1, 1, 1, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Neon_c_g_h

- **Used on** 209 part(s) in 78 model(s): vehicles (78)
- **Parts**: `e_licenseplate_back`, `e_interior`, `e_licenseplate_front`, `e_licenseplate_rear`, `defaultelement`, `e_exterior`
- **For example** `acschnitzer_acs1coupe_stock.model`, `chevrolet_camaro_stock.model`, `chevrolet_camaross_stock_rymer.model`, `bmw_1seriestii_race_natalya.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_MeshTexture` | texture | `cali_09`, `cali_13`, `cali_06`, `cali_04` |
| `g_vMtlParameters` | number × 8 | 0.194, 1, 1, 1, 1, 0, 0, 0 |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Neon_c_h

- **Used on** 2 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_headlightcover_frontleft`, `e_headlightcover_frontright`
- **For example** `volkswagen_golfw12650_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DamageTexture` | texture | `w12_interior` |
| `g_vMtlParameters` | number × 8 | 0.194, 1, 1, 1, 1, 0, 0, 0 |
| `g_MeshTexture` | texture | `w12_lights` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_paint

- **Used on** 6 part(s) in 5 model(s): vehicles (5)
- **Parts**: `e_bumper_front`, `e_bumper_back`, `e_boot`, `e_bonnet`
- **For example** `volkswagen_beetle_offroad.model`, `renault_meganesportr26_stock_shannon.model`, `renault_meganesportr26_stock.model`, `nissan_skyliner34ztune_stock_harumi.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent` |
| `g_vMtlParameters` | number × 8 | 0.09, 0.6, 1, 1, 0, 0, 0, 0 |
| `g_ScratchTexture` | texture | `r26-scratch`, `baja_scratch_1024`, `nismo_scratch` |
| `g_MeshTexture` | texture | `layara baja_1024`, `r26_livery`, `r26_livery_team_alpha`, `rin_livery` |
| `g_BumpTexture` | texture | `r26-bump_crop`, `baja_beetle_two`, `nismo_bump` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_a

- **Used on** 2 part(s) in 2 model(s): vehicles (2)
- **Parts**: `e_bumper_front`, `e_bumper_back`
- **For example** `audi_s3_stock.model`, `nissan_skyliner34ztune_stock.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent` |
| `g_vMtlParameters` | number × 8 | 0.09, 0.6, 1, 1, 0, 0, 0, 0 |
| `g_ScratchTexture` | texture | `audis3_scratch`, `nismo_scratch` |
| `g_BumpTexture` | texture | `petrol_bump`, `nismo_bump` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_a_b

- **Used on** 165 part(s) in 44 model(s): vehicles (44)
- **Parts**: `e_bonnet`, `e_bumper_front`, `e_bumper_back`, `e_wing_left`, `e_wing_right`, `e_boot`, `e_wing_frontleft`, `e_wing_frontright`
- **For example** `hennessey_vipervenom1000coupe_stock.model`, `chevrolet_camaross_drag.model`, `dodge_challenger_race.model`, `ford_focusrs_race.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent`, `DefaultColour` |
| `g_ScratchTexture` | texture | `dodge_viper_h_scratch`, `dodge_racer_scratch`, `focusrsrace_scratch`, `dodge_viper_scratch` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_a_b_c

- **Used on** 238 part(s) in 47 model(s): vehicles (47)
- **Parts**: `e_exterior`, `e_door_right`, `e_door_left`, `e_boot`, `e_mirror_right`, `e_mirror_left`, `e_wing_frontleft`, `e_wing_frontright`, `e_door_frontright`, `e_door_frontleft`
- **For example** `nissan_350z_drift.model`, `volkswagen_golfw12650_stock.model`, `ford_f150_offroad.model`, `audi_r8v10_stock.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent`, `DefaultColour` |
| `g_ScratchTexture` | texture | `DefaultColour`, `bmw_tii_race_scratch`, `nissan_350z_drift_scratch`, `w12_scratch` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_a_b_c_h

- **Used on** 42 part(s) in 25 model(s): vehicles (25)
- **Parts**: `e_interior`, `e_exterior`, `e_mirror_left`, `e_mirror_right`, `e_steeringwheel`, `e_mirror_centre`, `e_headlight_frontleft`, `e_headlight_frontright`, `e_mirror_center`, `e_door_left`
- **For example** `ford_mustanggtr_stock.model`, `volkswagen_beetle_offroad.model`, `ford_mustanggtr_legend_x.model`, `chevrolet_camaro_stock.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent`, `DefaultColour` |
| `g_ScratchTexture` | texture | `DefaultColour`, `corvette_zr1_scratch`, `ccxr_rgb_scratch`, `fordf100_scratch` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_a_b_h

- **Used on** 2 part(s) in 2 model(s): vehicles (2)
- **Parts**: `e_bumper_front`, `e_bumper_back`
- **For example** `ford_f150_offroad.model`, `ford_focusrs_stock.model`
- **Vertex data**: position, normal, UV, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `DefaultColour`, `paintdent` |
| `g_ScratchTexture` | texture | `f150offroad_scratch`, `focusrs_scratch` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_a_c

- **Used on** 7 part(s) in 6 model(s): vehicles (6)
- **Parts**: `e_exterior`, `e_boot`
- **For example** `nissan_skyliner34ztune_stock.model`, `shelby_mustanggt500_stock.model`, `ford_bronco_offroad.model`, `audi_s3_stock.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0.09, 0.6, 1, 1, 1, 0, 0, 0 |
| `g_DentTexture` | texture | `paintdent` |
| `g_BumpTexture` | texture | `nismo_bump`, `petrol_cap`, `broncotex_2`, `petrol_bump` |
| `g_ScratchTexture` | texture | `nismo_scratch`, `rgb_scratch_test`, `DefaultColour`, `audis3_scratch` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_a_c_h

- **Used on** 1 part(s) in 1 model(s): vehicles (1)
- **Parts**: `e_exterior`
- **For example** `volkswagen_beetle_offroad.model`
- **Vertex data**: position, normal, UV, UV 2, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_vMtlParameters` | number × 8 | 0, 0, 1, 1, 0.2, 0.2, 0.2, 1 |
| `g_DentTexture` | texture | `DefaultColour` |
| `g_BumpTexture` | texture | `texture 8` |
| `g_ScratchTexture` | texture | `DefaultColour` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_paint_b

- **Used on** 154 part(s) in 42 model(s): vehicles (42)
- **Parts**: `e_bonnet`, `e_bumper_front`, `e_bumper_back`, `e_wing_right`, `e_wing_left`, `e_boot`, `e_wing_frontleft`, `e_wing_frontright`
- **For example** `vauxhall_monarovxr_legend_iv.model`, `dodge_viperacr_legend_iii.model`, `opel_astraextreme_stock_shannon.model`, `dodge_challenger_tuner.model`
- **Vertex data**: position, normal, UV, damage offsets, damage control points, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent` |
| `g_ScratchTexture` | texture | `opelastraextreme_scratch`, `manaro_scratch`, `chevrolet_camaro_scratches`, `gt500_scratch` |
| `g_MeshTexture` | texture | `carbonfibre`, `legend03_dodge_viper_acr_stock`, `aotexture_blue`, `fordgt_livery1` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_paint_b_c

- **Used on** 208 part(s) in 43 model(s): vehicles (43)
- **Parts**: `e_exterior`, `e_boot`, `e_door_right`, `e_door_left`, `e_mirror_right`, `e_mirror_left`, `e_wing_frontleft`, `e_wing_frontright`, `e_door_frontright`, `e_door_frontleft`
- **For example** `chevrolet_camaro_rat.model`, `nissan_350znismo_stock.model`, `nissan_skyliner34ztune_stock_harumi.model`, `volkswagen_beetle_rat.model`
- **Vertex data**: position, normal, UV, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent` |
| `g_MeshTexture` | texture | `camaro_rat_base`, `rin_livery`, `rust texture`, `rin_livery_yellow` |
| `g_ScratchTexture` | texture | `nismo_scratch`, `r26-scratch`, `chevrolet_camaro_scratches`, `camaro_rat_scratch` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Paint_b_c_h

- **Used on** 37 part(s) in 17 model(s): vehicles (17)
- **Parts**: `e_exterior`, `e_interior`, `e_door_left`, `e_door_right`, `e_mirror_left`, `e_mirror_right`, `e_wiper_frontleft`, `e_wiper_frontright`, `e_wing_right`, `e_wing_left`
- **For example** `bmw_1seriestii_stock.model`, `nissan_350znismo_stock.model`, `audi_s3_stock.model`, `ford_bronco_offroad.model`
- **Vertex data**: position, normal, UV, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent` |
| `g_MeshTexture` | texture | `bmw_tii_livery`, `nissan_350z_nismo_livery_512`, `breakdisc`, `broncotex_1` |
| `g_ScratchTexture` | texture | `DefaultColour`, `bmw_tii_scratch`, `nissan_350z_nismo_scratch`, `lotus_260_scratch` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_paint_c

- **Used on** 9 part(s) in 6 model(s): vehicles (6)
- **Parts**: `e_exterior`, `e_boot`, `e_door_right`, `e_door_left`
- **For example** `volkswagen_beetle_offroad.model`, `nissan_skyliner34ztune_stock_harumi.model`, `nissan_skyliner34ztune_stock_ayumi.model`, `chevrolet_camaross_stock_rymer.model`
- **Vertex data**: position, normal, UV, UV 2, damage offsets, colour

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_DentTexture` | texture | `paintdent` |
| `g_vMtlParameters` | number × 8 | 0.09, 0.6, 1, 1, 1, 0, 0, 0 |
| `g_ScratchTexture` | texture | `nismo_scratch`, `chevrolet_camaro_scratches`, `baja_scratch_1024`, `nissan_350z_nismo_scratch` |
| `g_MeshTexture` | texture | `layara baja_1024`, `rin_livery`, `rin_livery_yellow`, `chevrolet_camaro_rhymer_liv` |
| `g_BumpTexture` | texture | `nismo_bump`, `chevrolet_camaro_1`, `baja_beetle_two`, `bump` |

Also a pass with `g_LocalSpaceSHNode`, `g_vCodeDamageScale` (set by the game).

### veh_Shadow

- **Used on** 81 part(s) in 80 model(s): vehicles (80)
- **Parts**: `defaultelement`
- **For example** `hummer_h2_rat.model`, `acschnitzer_acs1coupe_stock.model`, `chevrolet_camaro_stock.model`, `chevrolet_camaross_stock_rymer.model`
- **Vertex data**: position

### Water_NL_NV

- **Used on** 3 part(s) in 1 model(s): objects: usa_la_river (1)
- **Parts**: `defaultelement`
- **For example** `dynamicwaterlevel.model`
- **Vertex data**: position, normal, UV

| Input | Kind | Usual value / textures |
|---|---|---|
| `g_fWaterRefractAmount` | number × 4 | 0.1, 0, 0, 0 |
| `g_tNormal` | texture | `waterripples_norm` |
| `g_fWaterExtinctionScale` | number × 4 | 0.008, 0, 0, 0 |
| `g_vNormalVelocity1` | number × 4 | 0.06, 0.43, 0, 0 |
| `g_vNormalScale0` | number × 4 | 560, 560, 0, 0 |
| `g_vNormalScale1` | number × 4 | 340, 340, 0, 0 |
| `g_vNormalVelocity0` | number × 4 | -0.003, 0.41, 0, 0 |
| `g_tBlendNormal` | texture | `waterripples_norm` |
| `g_fWaterSpecularIntensity` | number × 4 | 0.25, 0, 0, 0 |
| `g_vWaterColour` | number × 4 | 0.58, 0.503, 0.341, 0 |
