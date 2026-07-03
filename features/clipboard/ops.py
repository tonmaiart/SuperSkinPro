# Copyright (c) 2026 Natchapon Srisuk. All rights reserved.
import bpy
from ...core.facade import CoreFacade
from ...interface.utils.op_exec import run_domain_via_unified

# ==============================================================================
# VERTEX OPERATORS (Smart Auto-Detect)
# ==============================================================================

class OBJECT_OT_ssp_copy_weight(bpy.types.Operator):
    bl_idname = "object.ssp_copy_weight"
    bl_label = "Copy Weight"
    bl_description = "Copy weight data based on active UI context automatically"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return run_domain_via_unified(context, "clipboard", "copy")


class OBJECT_OT_ssp_cut_weight(bpy.types.Operator):
    bl_idname = "object.ssp_cut_weight"
    bl_label = "Cut Weight"
    bl_description = "Cut weight data based on active UI context automatically"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "clipboard", "cut")


class OBJECT_OT_ssp_paste_weight_add(bpy.types.Operator):
    bl_idname = "object.ssp_paste_weight_add"
    bl_label = "Paste Weight (Add)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "clipboard", "paste_add")


class OBJECT_OT_ssp_paste_weight_subtract(bpy.types.Operator):
    bl_idname = "object.ssp_paste_weight_subtract"
    bl_label = "Paste Weight (Subtract)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "clipboard", "paste_subtract")


class OBJECT_OT_ssp_paste_weight_replace(bpy.types.Operator):
    bl_idname = "object.ssp_paste_weight_replace"
    bl_label = "Paste Weight (Replace)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "clipboard", "paste_replace")


# ==============================================================================
# 🌟 DATA OPERATORS (Manual Control via Enum Settings)
# ==============================================================================

class OBJECT_OT_ssp_clipboard_data_copy(bpy.types.Operator):
    bl_idname = "object.ssp_clipboard_data_copy"
    bl_label = "Copy/Cut Data Manual"
    bl_options = {'REGISTER', 'UNDO'}
    
    action_type: bpy.props.EnumProperty(
        items=[('COPY', "Copy", ""), ('CUT', "Cut", "")],
        default='COPY'
    )

    def execute(self, context):
        from . import logic
        try:
            logic.copy_data_manual(CoreFacade(context), action=self.action_type)
        except ValueError as e:
            self.report({'WARNING'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_ssp_clipboard_data_paste(bpy.types.Operator):
    bl_idname = "object.ssp_clipboard_data_paste"
    bl_label = "Paste Data Manual"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import logic
        prefs = context.window_manager.superskin_clipboard_prefs
        
        context.scene.superskin_internal_transaction = True
        try:
            logic.paste_data_manual(CoreFacade(context), mode=prefs.paste_operation)
        except ValueError as e:
            self.report({'WARNING'}, str(e))
            return {'CANCELLED'}
        finally:
            context.scene.superskin_internal_transaction = False
        return {'FINISHED'}


# ==============================================================================
# REGISTRATION
# ==============================================================================

_classes = (
    OBJECT_OT_ssp_copy_weight,
    OBJECT_OT_ssp_cut_weight,
    OBJECT_OT_ssp_paste_weight_add,
    OBJECT_OT_ssp_paste_weight_subtract,
    OBJECT_OT_ssp_paste_weight_replace,
    OBJECT_OT_ssp_clipboard_data_copy,
    OBJECT_OT_ssp_clipboard_data_paste,
)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)