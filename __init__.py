"""Blur Model Tools: Blur (2010) .model files in Blender.

File > Import > Blur Model (.model) brings in a model with its part hierarchy,
materials (Blur effects as node groups) and the textures stored in it.
File > Export > Blur Model (.model) writes it back with the meshes' edits.
Material Properties > Blur Material picks a Blur effect for any material and
wires up its texture slots.
"""

import os
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import exporter, importer, materials
from .blur import model as blurmodel


class BLUR_OT_import_model(bpy.types.Operator, ImportHelper):
    """Import a Blur .model file (parts, materials and textures)"""

    bl_idname = "import_scene.blur_model"
    bl_label = "Import Blur Model"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    filename_ext = ".model"
    filter_glob: StringProperty(default="*.model", options={"HIDDEN"})
    all_lods: BoolProperty(name="All Detail Levels", default=False,
                           description="Also import the lower detail levels (each in its own hidden collection)")
    shadows: BoolProperty(name="Shadow Hulls", default=True,
                          description="Import the shadow hulls (hidden collection)")
    collisions: BoolProperty(name="Collision", default=True,
                             description="Import the collision shapes (hidden collection; each triangle's "
                                         "surface, e.g. Metal or Glass, is its material)")

    def execute(self, context):
        started = time.perf_counter()
        try:
            importer.import_model(context, self.filepath, self.all_lods, self.shadows, self.collisions)
        except (blurmodel.ModelError, OSError) as e:
            self.report({"ERROR"}, f"Can't import {self.filepath}: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported {os.path.basename(self.filepath)} in {time.perf_counter() - started:.1f} s")
        return {"FINISHED"}


def _roots(context):
    """The imported model to export: the active object's, else the one the selection belongs
    to, else the scene's (any one object of a model is enough, nothing needs selecting when
    the scene holds one model)."""
    active = exporter.model_root(context.active_object)
    if active is not None:
        return [active]
    picked = {exporter.model_root(o) for o in context.selected_objects}
    picked.discard(None)
    if not picked:
        picked = {o for o in context.scene.objects if "blur_model" in o}
    return sorted(picked, key=lambda o: o.name)


class BLUR_OT_export_model(bpy.types.Operator, ExportHelper):
    """Write the imported Blur model back, with the meshes' edits (geometry of existing parts)"""

    bl_idname = "export_scene.blur_model"
    bl_label = "Export Blur Model"

    filename_ext = ".model"
    filter_glob: StringProperty(default="*.model", options={"HIDDEN"})
    source: StringProperty(name="Original Model", subtype="FILE_PATH",
                           description="The .model file this was imported from: the export starts from it "
                                       "and replaces the edited parts")

    @classmethod
    def poll(cls, context):
        return bool(_roots(context))

    def invoke(self, context, event):
        roots = _roots(context)
        if len(roots) == 1:
            self.source = roots[0]["blur_model"]
            base = os.path.splitext(os.path.basename(self.source))[0]
            self.filepath = os.path.join(os.path.dirname(self.source), base + "_edited.model")
        return super().invoke(context, event)

    def execute(self, context):
        roots = _roots(context)
        if len(roots) != 1:
            self.report({"ERROR"}, "Several Blur models here: click any object of the one to export")
            return {"CANCELLED"}
        root = roots[0]
        source = bpy.path.abspath(self.source or root["blur_model"])
        if not os.path.isfile(source):
            self.report({"ERROR"}, f"The original model isn't at {source}: point Original Model at it")
            return {"CANCELLED"}
        if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(self.filepath)):
            self.report({"ERROR"}, "Export to a new file: the original model is what the export starts from")
            return {"CANCELLED"}
        started = time.perf_counter()
        try:
            exporter.export_model(context, root, source, self.filepath)
        except (exporter.ExportError, blurmodel.ModelError, OSError) as e:
            self.report({"ERROR"}, f"Can't export: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {os.path.basename(self.filepath)} in {time.perf_counter() - started:.1f} s")
        return {"FINISHED"}


def _effect_items(self, context):
    items = []
    by_cat = {}
    for effect in sorted(materials.presets(), key=str.lower):
        by_cat.setdefault(materials.category(effect), []).append(effect)
    for cat in ("Vehicle", "World", "Characters", "Effects"):
        for effect in by_cat.get(cat, []):
            p = materials.presets()[effect]
            desc = f"{cat}: used on {p['parts']} part(s) in {p['models']} model(s)"
            items.append((effect, effect.rsplit(".", 1)[0], desc))
    return items or [("NONE", "No presets", "presets/effects.json is missing")]


class BLUR_OT_set_effect(bpy.types.Operator):
    """Make the active material a Blur material drawn with the chosen effect"""

    bl_idname = "material.blur_set_effect"
    bl_label = "Set Blur Effect"
    bl_property = "effect"
    bl_options = {"REGISTER", "UNDO"}

    effect: EnumProperty(name="Effect", items=_effect_items)

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if self.effect == "NONE":
            return {"CANCELLED"}
        obj = context.object
        mat = obj.active_material
        if mat is None:
            mat = materials.new_material(self.effect)
            if obj.material_slots:
                obj.material_slots[obj.active_material_index].material = mat
            else:
                obj.data.materials.append(mat)
        else:
            materials.setup_material(mat, self.effect)
        self.report({"INFO"}, f"{mat.name}: {self.effect}")
        return {"FINISHED"}


class BLUR_OT_open_texture(bpy.types.Operator, ImportHelper):
    """Load a picture from disk into this texture slot (replaces the one there)"""

    bl_idname = "material.blur_open_texture"
    bl_label = "Open Texture"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default="*.dds;*.png;*.jpg;*.jpeg;*.tga;*.bmp;*.tif;*.tiff",
                                options={"HIDDEN"})
    input_name: StringProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.active_material is not None

    def execute(self, context):
        mat = context.object.active_material
        try:
            img = bpy.data.images.load(self.filepath, check_existing=True)
        except RuntimeError as e:
            self.report({"ERROR"}, f"Can't open {self.filepath}: {e}")
            return {"CANCELLED"}
        if not materials.assign_image(mat, self.input_name, img):
            self.report({"ERROR"}, f"{mat.name} has no {self.input_name} slot")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{self.input_name}: {img.name}")
        return {"FINISHED"}


class BLUR_PT_material(bpy.types.Panel):
    bl_label = "Blur Material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def draw(self, context):
        layout = self.layout
        mat = context.object.active_material
        effect = materials.material_effect(mat) if mat else ""
        row = layout.row()
        row.operator(BLUR_OT_set_effect.bl_idname, text=effect.rsplit(".", 1)[0] if effect else "Choose Blur Effect…",
                     icon="MATERIAL")
        if not mat or not effect:
            layout.label(text="Pick a Blur effect to set this material up for export.")
            return
        node = materials.group_node(mat)
        if node is None:
            layout.label(text="The Blur Shader node is missing: choose the effect again.", icon="ERROR")
            return
        preset = materials.presets().get(effect)
        if preset is None:
            layout.label(text="Not a known effect (kept as imported).", icon="INFO")
        preview = materials.preview_image(mat)
        if preview is not None:
            box = layout.box()
            row = box.row()
            row.prop(preview, "generated_color", text="Viewport colour")
            if effect.lower().startswith("veh_paint"):
                box.label(text="Paint has no colour texture: the game picks the colour.", icon="INFO")
        box = layout.box()
        box.label(text="Textures", icon="TEXTURE")
        for input_name in materials.texture_inputs(effect):
            tex = mat.node_tree.nodes.get(input_name)
            col = box.column(align=True)
            col.label(text=input_name)
            if tex is not None and tex.type == "TEX_IMAGE":
                row = col.row(align=True)
                row.template_ID(tex, "image")
                op = row.operator(BLUR_OT_open_texture.bl_idname, text="", icon="FILEBROWSER")
                op.input_name = input_name
            if preset:
                usual = preset.get("textures", {}).get(input_name)
                if usual:
                    col.label(text="Game uses: " + ", ".join(usual[:3]), icon="INFO")
        numbers = [s for s in node.inputs if not s.is_linked and s.type in ("VALUE", "INT")]
        if numbers:
            box = layout.box()
            box.label(text="Parameters", icon="PROPERTIES")
            for sock in numbers:
                box.prop(sock, "default_value", text=sock.name)


def menu_import(self, context):
    self.layout.operator(BLUR_OT_import_model.bl_idname, text="Blur Model (.model)")


def menu_export(self, context):
    self.layout.operator(BLUR_OT_export_model.bl_idname, text="Blur Model (.model)")


classes = (BLUR_OT_import_model, BLUR_OT_export_model, BLUR_OT_set_effect, BLUR_OT_open_texture,
           BLUR_PT_material)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
