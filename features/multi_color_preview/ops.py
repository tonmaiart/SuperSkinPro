"""Operator shells for the multi_color_preview feature domain."""

import bpy
from ...shared.op_exec import run_domain


class SUPERSKIN_OT_toggle_multi_color(bpy.types.Operator):
    bl_idname = "superskin.toggle_multi_color"
    bl_label = "Toggle Multi Color Preview"

    def execute(self, context):
        return run_domain(context, "toggle_multi_color")


_classes = (SUPERSKIN_OT_toggle_multi_color,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
