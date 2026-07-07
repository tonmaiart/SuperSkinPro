"""SuperSkinPro main sidebar panel — interface-split UI.

Content adapts to ``WindowManager.superskin_active_interface`` (owned and
registered by this module), not to Blender's native interaction mode:
  LAYER    -> LayerViewer + "Edit Layer Weight" gate button.
  SKINNING -> DeformBoneViewer + tool sections + "Save Weights" gate button.

This state is deliberately decoupled from ``context.mode`` — pressing Tab
does not by itself change which interface is shown; only the explicit
"Edit Layer Weight" / "Save Weights" operators (and the auto-save guard's
unguarded-exit detection) flip it. See ``features/controller/ops_scene_modes.py``.

System/Customize settings are rendered in the "Preference" sidebar panel
(``panel_gate.py``) instead of here, keeping this panel focused on artwork
operations.
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
        from ..core.facade import CoreFacade
        return context.mode in ('OBJECT', 'EDIT_MESH') and CoreFacade.is_system_activated()

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if not (obj and obj.type == "MESH"):
            layout.label(text="No mesh active", icon="ERROR")
            return

        widget_preferences.draw_mode_split_ui(layout, context)


def register():
    bpy.types.WindowManager.superskin_active_interface = bpy.props.EnumProperty(
        name="Active Interface",
        description="Which SuperSkinPro sidebar interface is currently shown, "
                    "decoupled from Blender's native Object/Edit mode",
        items=[
            ('LAYER', "Layer", "Show the Layer weight-management interface"),
            ('SKINNING', "Skinning", "Show the Skinning/weight-painting interface"),
        ],
        default='LAYER',
        options={'SKIP_SAVE'},
    )
    bpy.utils.register_class(VIEW3D_PT_mw_master_modular_panel)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_mw_master_modular_panel)
    del bpy.types.WindowManager.superskin_active_interface
