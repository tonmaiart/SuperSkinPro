"""SuperSkinPro main sidebar panel — mode-split UI.

Content adapts to the active Blender interaction mode:
  OBJECT mode  -> LayerViewer + "Edit Layer Weight" gate button.
  EDIT_MESH    -> DeformBoneViewer + tool sections + "Save Weights" gate button.

System/Customize settings are rendered in the native Blender Add-on Preferences
panel instead of here, keeping the sidebar focused on artwork operations.
"""

import bpy

from . import widget_preferences


class VIEW3D_PT_mw_master_modular_panel(bpy.types.Panel):
    bl_idname = "VIEW3D_PT_superskin_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Super Skin Pro'
    bl_label = "Super Skin Pro"
    bl_order = 1000000

    @classmethod
    def poll(cls, context):
        return context.mode in ('OBJECT', 'EDIT_MESH')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if not (obj and obj.type == "MESH"):
            layout.label(text="No mesh active", icon="ERROR")
            return

        widget_preferences.draw_mode_split_ui(layout, context)


def register():
    bpy.utils.register_class(VIEW3D_PT_mw_master_modular_panel)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_mw_master_modular_panel)
