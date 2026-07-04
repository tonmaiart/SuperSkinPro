"""Modal operator for interactive circle brush radius adjustment."""

import bpy


class SUPERSKIN_OT_circle_tool_adjust_radius(bpy.types.Operator):
    """Drag mouse horizontally to resize the circle selection brush."""
    bl_idname = "superskin.circle_tool_adjust_radius"
    bl_label = "Adjust Circle Tool Radius"
    bl_options = {'REGISTER', 'UNDO'}

    _initial_x: int = 0
    _initial_y: int = 0
    _backup_radius: int = 30

    def modal(self, context, event):
        prefs = context.window_manager.superskin_circle_tool_adjust_prefs

        if event.type == 'MOUSEMOVE':
            delta = event.mouse_x - self._initial_x
            if delta != 0:
                new_radius = max(1, min(300, prefs.brush_radius_value + int(delta * 0.3)))
                prefs.brush_radius_value = new_radius
                context.area.header_text_set(f"Brush Radius: {new_radius}")
                context.window.cursor_warp(self._initial_x, self._initial_y)

        elif event.type == self._trigger_type and event.value == 'RELEASE':
            context.window.cursor_modal_restore()
            context.area.header_text_set(None)
            return {'FINISHED'}

        elif event.type == 'ESC':
            context.window.cursor_modal_restore()
            prefs.brush_radius_value = self._backup_radius
            context.area.header_text_set(None)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if context.space_data.type != 'VIEW_3D':
            return {'CANCELLED'}
        prefs = context.window_manager.superskin_circle_tool_adjust_prefs
        self._trigger_type = event.type
        self._initial_x = event.mouse_x
        self._initial_y = event.mouse_y
        self._backup_radius = prefs.brush_radius_value
        context.window.cursor_modal_set('NONE')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


_classes = (SUPERSKIN_OT_circle_tool_adjust_radius,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
