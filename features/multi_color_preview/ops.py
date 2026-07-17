"""Operator shells for the multi_color_preview feature domain."""

import bpy
from ...interface.utils.op_exec import run_domain_via_unified


class SUPERSKIN_OT_toggle_multi_color(bpy.types.Operator):
    """Hold Alt+3 to preview multi-bone color; releasing it stops the
    preview. Previously a plain press-to-toggle action (`toggle_multi_color`)
    -- now a hold gesture using `start_multi_color`/`stop_multi_color`
    directly, matching the "hold while active" pattern of this addon's
    other keymap-driven modal gestures (weight_apply, circle_tool_adjust).

    Only intercepts its own trigger key's RELEASE event -- every other
    event is passed through (`PASS_THROUGH`) so holding Alt+3 doesn't block
    viewport navigation or any other input while the preview is active.
    """
    bl_idname = "superskin.toggle_multi_color"
    bl_label = "Multi Color Preview (Hold)"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self._trigger_type = event.type
        run_domain_via_unified(context, "multi_color_preview", "start_multi_color")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == self._trigger_type and event.value == 'RELEASE':
            run_domain_via_unified(context, "multi_color_preview", "stop_multi_color")
            return {'FINISHED'}
        return {'PASS_THROUGH'}


_classes = (SUPERSKIN_OT_toggle_multi_color,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
