"""Blur materials in Blender.

Every Blur effect (veh_Paint_a.fx, veh_Glass_c_h.fx, default_NB...) becomes a
node group "Blur: <effect>" with one input socket per input the game gives
that effect: textures (plug an Image Texture node into them) and numbers
(g_vMtlParameters 0..7, ...). A material made from a preset holds that group,
wired to the Material Output, plus an Image Texture node per texture input,
so you only pick images. Inside, the group approximates the look with a
Principled BSDF (colour texture, normal map, alpha); the game's own shading is
not reproduced.

Which inputs an effect has, their usual values and which textures the game
puts in them come from presets/effects.json (tools/scan_effects.py, from every
model in the game). The exporter reads the group's sockets back: texture
inputs from the linked Image Texture nodes, numbers from the socket values.
"""

import json
import os

import bpy

PRESETS_FILE = os.path.join(os.path.dirname(__file__), "presets", "effects.json")
GROUP_PREFIX = "Blur: "

_presets = None


def presets():
    """effect name -> preset (see tools/scan_effects.py)."""
    global _presets
    if _presets is None:
        try:
            with open(PRESETS_FILE, encoding="utf-8") as fh:
                _presets = json.load(fh)
        except OSError:
            _presets = {}
    return _presets


def category(effect):
    """Menu section for an effect."""
    low = effect.lower()
    if low.startswith("veh_"):
        return "Vehicle"
    if "skin" in low:
        return "Characters"
    if low.startswith(("mesheffect", "screenfacing", "lightflare", "softlightflare", "carlightflare",
                       "flashinglightflare")):
        return "Effects"
    return "World"


def main_inputs(effect):
    """The inputs of the effect's main pass: [(name, type, count)]."""
    preset = presets().get(effect)
    if not preset or not preset["passes"]:
        return []
    return [(i["name"], i["type"], i["count"]) for i in preset["passes"][0]["inputs"]]


_ROLES = {
    "g_talbedo": "color", "g_meshtexture": "color", "g_tcolour": "color", "g_ttexture": "color",
    "g_sofftexture": "color",
    "g_tnormal": "normal", "g_bumptexture": "normal",
    "g_tneon": "emission", "g_sontexture": "emission",
}


def texture_role(name):
    """How the preview uses a texture input: 'color', 'normal', 'emission' or None (damage,
    scratches, material maps, distortion... aren't part of the preview)."""
    return _ROLES.get(name.lower())


def number_sockets(name, count):
    """Socket names for a number input of `count` values."""
    if count == 1:
        return [name]
    return [f"{name} {i}" for i in range(count)]


# ---- node groups ---------------------------------------------------------------------------

def effect_group(effect):
    """The node group for `effect`, made on first use."""
    name = GROUP_PREFIX + effect
    group = bpy.data.node_groups.get(name)
    if group is not None:
        return group
    group = bpy.data.node_groups.new(name, "ShaderNodeTree")
    group["blur_effect"] = effect
    iface = group.interface
    iface.new_socket("BSDF", in_out="OUTPUT", socket_type="NodeSocketShader")

    preset = presets().get(effect, {})
    defaults = preset.get("defaults", {})
    color_socket = normal_socket = emission_socket = None
    for input_name, kind, count in main_inputs(effect):
        if kind in ("texture", "texture_ptr"):
            sock = iface.new_socket(input_name, in_out="INPUT", socket_type="NodeSocketColor")
            sock.default_value = (0.8, 0.8, 0.8, 1.0)
            alpha = iface.new_socket(input_name + " Alpha", in_out="INPUT", socket_type="NodeSocketFloat")
            alpha.default_value = 1.0
            alpha.hide_value = True
            role = texture_role(input_name)
            if role == "color" and color_socket is None:
                color_socket = input_name
            elif role == "normal" and normal_socket is None:
                normal_socket = input_name
            elif role == "emission" and emission_socket is None:
                emission_socket = input_name
        elif kind == "f32":
            values = defaults.get(input_name, [0.0] * count)
            for i, sock_name in enumerate(number_sockets(input_name, count)):
                sock = iface.new_socket(sock_name, in_out="INPUT", socket_type="NodeSocketFloat")
                sock.default_value = values[i] if i < len(values) else 0.0
        elif kind in ("s8", "u8", "s16", "u16", "s32", "u32"):
            values = defaults.get(input_name, [0] * count)
            for i, sock_name in enumerate(number_sockets(input_name, count)):
                sock = iface.new_socket(sock_name, in_out="INPUT", socket_type="NodeSocketInt")
                sock.default_value = int(values[i]) if i < len(values) else 0
        # "data" inputs (lighting, wheel spin...) are filled in by the game, not the material

    nodes, links = group.nodes, group.links
    inp = nodes.new("NodeGroupInput")
    inp.location = (-600, 0)
    out = nodes.new("NodeGroupOutput")
    out.location = (400, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["BSDF"])
    low = effect.lower()
    if low.startswith("veh_glass"):
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Alpha"].default_value = 0.35
    elif low.startswith(("veh_paint", "veh_alloy")):
        bsdf.inputs["Metallic"].default_value = 0.6
        bsdf.inputs["Roughness"].default_value = 0.25
    elif low.startswith(("veh_light", "veh_neon", "animatedneon")):
        bsdf.inputs["Emission Strength"].default_value = 1.0
    if color_socket:
        links.new(inp.outputs[color_socket], bsdf.inputs["Base Color"])
        if low.startswith(("veh_neon", "meshe", "lightflare", "softlightflare", "carlightflare", "flashing")):
            links.new(inp.outputs[color_socket], bsdf.inputs["Emission Color"])
        if low.startswith(("veh_alpha", "veh_glass", "mesheffect", "lightflare", "softlightflare", "carlightflare",
                           "flashing", "screenfacing")) or "alpha" in low:
            links.new(inp.outputs[color_socket + " Alpha"], bsdf.inputs["Alpha"])
    elif low.startswith(("veh_paint", "veh_shadow")):
        bsdf.inputs["Base Color"].default_value = (0.25, 0.3, 0.45, 1.0)  # the game picks the paint colour
    if emission_socket:
        links.new(inp.outputs[emission_socket], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.0
    if normal_socket:
        nmap = nodes.new("ShaderNodeNormalMap")
        nmap.location = (-250, -300)
        links.new(inp.outputs[normal_socket], nmap.inputs["Color"])
        links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return group


def texture_inputs(effect):
    return [n for n, kind, _ in main_inputs(effect) if kind in ("texture", "texture_ptr")]


def new_material(effect, name=None, images=None, values=None):
    """A material drawn with `effect`: its group, an Image Texture node per texture input
    (filled from `images`: input name -> bpy image) and number values (`values`:
    input name -> [floats])."""
    mat = bpy.data.materials.new(name or effect.rsplit(".", 1)[0])
    mat.use_backface_culling = True   # Blur draws front faces only (two-sided parts have both)
    setup_material(mat, effect, images, values)
    return mat


def setup_material(mat, effect, images=None, values=None):
    """(Re)builds `mat`'s nodes for `effect`, keeping the images already plugged in where
    the new effect has an input of the same name."""
    images = dict(images or {})
    if getattr(mat, "node_tree", None) is None and hasattr(mat, "use_nodes"):
        mat.use_nodes = True
    tree = mat.node_tree
    old = group_node(mat)
    if old is not None:  # keep what's plugged in
        for sock in old.inputs:
            if sock.is_linked and sock.links[0].from_node.type == "TEX_IMAGE":
                img = sock.links[0].from_node.image
                if img is not None:
                    images.setdefault(sock.name, img)
    tree.nodes.clear()
    group = effect_group(effect)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    node = tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    node.name = node.label = "Blur Shader"
    node.width = 260
    node.location = (0, 0)
    tree.links.new(node.outputs["BSDF"], out.inputs["Surface"])
    y = 300
    active = None
    for input_name in texture_inputs(effect):
        tex = tree.nodes.new("ShaderNodeTexImage")
        tex.name = tex.label = input_name
        tex.location = (-420, y)
        y -= 280
        img = images.get(input_name)
        if img is not None:
            tex.image = img
            if texture_role(input_name) != "color":
                img.colorspace_settings.name = "Non-Color"
        tree.links.new(tex.outputs["Color"], node.inputs[input_name])
        tree.links.new(tex.outputs["Alpha"], node.inputs[input_name + " Alpha"])
        if texture_role(input_name) == "color" and active is None:
            active = tex
    # Solid view and Workbench show the active image node: make it the colour texture
    tree.nodes.active = active or node
    for input_name, numbers in (values or {}).items():
        for i, sock_name in enumerate(number_sockets(input_name, len(numbers))):
            if sock_name in node.inputs:
                node.inputs[sock_name].default_value = numbers[i]
    mat["blur_effect"] = effect
    low = effect.lower()
    blended = low.startswith(("veh_glass", "veh_alpha")) or "alpha" in low
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED" if blended else "DITHERED"
    return node


def group_node(mat):
    """The material's Blur Shader node, or None."""
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return None
    for node in tree.nodes:
        if node.type == "GROUP" and node.node_tree is not None and "blur_effect" in node.node_tree:
            return node
    return None


def material_effect(mat):
    node = group_node(mat)
    return node.node_tree["blur_effect"] if node is not None else mat.get("blur_effect", "")
