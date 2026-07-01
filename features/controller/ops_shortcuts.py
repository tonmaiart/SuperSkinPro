"""Shortcuts for SuperSkinPro — pie menu operator.

Relocated from operators/ops_shortcuts.py to features/controller/ (2026-06).
"""

import bpy


# ==============================================================================
# PIE MENU (from pie_menu.py)
# ==============================================================================

class MW_MT_pie_menu(bpy.types.Menu):
    bl_label = "Super Skin Pro Quick Menu"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        # ── Non-EDIT modes: only structural utility toggles ──────────
        if context.mode not in {'EDIT_MESH'}:
            pie.separator()
            pie.separator()
            pie.separator()

            pie.operator("object.mw_toggle_edit_mode",
                         text="Enter Skin Mode", icon='MOD_VERTEX_WEIGHT')
            pie.operator("object.mw_force_pose_mode",
                         text="Enter Pose Mode", icon='POSE_HLT')
            return

        # ── EDIT_MESH mode: full weight-painting toolkit ─────────────
        pie.operator("mesh.select_more",
                     text="Grow", icon='ZOOM_IN')
        pie.operator("superskin.safe_shrink",
                     text="Shrink", icon='ZOOM_OUT')
        pie.separator()

        pie.operator("object.mw_toggle_edit_mode",
                     text="Exit Skin Mode", icon='MOD_VERTEX_WEIGHT')
        pie.operator("object.mw_force_pose_mode",
                     text="Enter Pose Mode", icon='POSE_HLT')
        pie.operator("object.mirror_weights",
                     text="Mirror Skin Weight", icon='MOD_MIRROR')
        pie.prop(context.space_data.shading,
                    "show_xray", text="Toggle X-Ray")


class MW_OT_call_pie(bpy.types.Operator):
    bl_idname = "object.mw_call_pie"
    bl_label = "Call Pie Menu"

    def execute(self, context):
        bpy.ops.wm.call_menu_pie(name="MW_MT_pie_menu")
        return {'FINISHED'}


addon_keymaps = []


# ==============================================================================
# REGISTRATION
# ==============================================================================

def register():
    bpy.utils.register_class(MW_MT_pie_menu)
    bpy.utils.register_class(MW_OT_call_pie)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon

    if kc:
        target_modes = ['Object Mode', 'Mesh', 'Pose', 'Weight Paint']
        for mode_name in target_modes:
            km = kc.keymaps.new(name=mode_name, space_type='EMPTY')
            kmi = km.keymap_items.new("object.mw_call_pie", type='ONE', value='PRESS', alt=True)
            addon_keymaps.append((km, kmi))


def unregister():
    bpy.utils.unregister_class(MW_OT_call_pie)
    bpy.utils.unregister_class(MW_MT_pie_menu)

    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
