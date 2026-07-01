"""Weight-apply operators — Add, Scale, Smooth, Sharpen + preset menus + preset setter."""

import bpy
from ...shared.op_exec import run_domain
from .weight_apply_feature import get_prefs


class OBJECT_OT_mw_add_weight(bpy.types.Operator):
    bl_idname = "object.mw_add_weight"
    bl_label = "Add Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain(context, "add")


class OBJECT_OT_mw_scale_weight(bpy.types.Operator):
    bl_idname = "object.mw_scale_weight"
    bl_label = "Scale Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain(context, "scale")


class OBJECT_OT_mw_smooth_weight(bpy.types.Operator):
    bl_idname = "object.mw_smooth_weight"
    bl_label = "Smooth Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain(context, "smooth")


class OBJECT_OT_mw_sharpen_weight(bpy.types.Operator):
    bl_idname = "object.mw_sharpen_weight"
    bl_label = "Sharpen Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain(context, "sharpen")


# ── Preset menus ──────────────────────────────────────────────────────────

def _draw_preset_menu(menu, context, op_type):
    layout = menu.layout
    groups = [
        [0.0],
        [0.001, 0.01, 0.1],
        [0.25, 0.5, 0.75],
        [0.9, 0.99, 0.999],
        [1.0],
    ]
    for i, group in enumerate(groups):
        if i > 0:
            layout.separator()
        for v in group:
            op = layout.operator("wm.set_op_weight_preset", text=str(v))
            op.op_type = op_type
            op.value = v


class SUPERSKIN_MT_add_presets(bpy.types.Menu):
    bl_label = "Add Presets"
    bl_idname = "SUPERSKIN_MT_add_presets"

    def draw(self, context):
        _draw_preset_menu(self, context, 'ADD')


class SUPERSKIN_MT_scale_presets(bpy.types.Menu):
    bl_label = "Scale Presets"
    bl_idname = "SUPERSKIN_MT_scale_presets"

    def draw(self, context):
        _draw_preset_menu(self, context, 'SCALE')


class SUPERSKIN_MT_smooth_presets(bpy.types.Menu):
    bl_label = "Smooth Presets"
    bl_idname = "SUPERSKIN_MT_smooth_presets"

    def draw(self, context):
        _draw_preset_menu(self, context, 'SMOOTH')


class SUPERSKIN_MT_sharpen_presets(bpy.types.Menu):
    bl_label = "Sharpen Presets"
    bl_idname = "SUPERSKIN_MT_sharpen_presets"

    def draw(self, context):
        _draw_preset_menu(self, context, 'SHARPEN')


# ── Preset setter (relocated from operators/ops_tools.py) ────────────────

class WM_OT_set_op_weight_preset(bpy.types.Operator):
    bl_idname = "wm.set_op_weight_preset"
    bl_label = "Set Op Weight Preset"
    bl_options = {'REGISTER', 'UNDO'}

    op_type: bpy.props.StringProperty()
    value: bpy.props.FloatProperty()

    def execute(self, context):
        p = get_prefs()
        prop_map = {
            'ADD':     'add_val',
            'SCALE':   'scale_val',
            'SMOOTH':  'smooth_val',
            'SHARPEN': 'sharpen_val',
        }
        prop = prop_map.get(self.op_type)
        if prop:
            setattr(p, prop, self.value)
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────

_classes = (
    OBJECT_OT_mw_add_weight,
    OBJECT_OT_mw_scale_weight,
    OBJECT_OT_mw_smooth_weight,
    OBJECT_OT_mw_sharpen_weight,
    SUPERSKIN_MT_add_presets,
    SUPERSKIN_MT_scale_presets,
    SUPERSKIN_MT_smooth_presets,
    SUPERSKIN_MT_sharpen_presets,
    WM_OT_set_op_weight_preset,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
