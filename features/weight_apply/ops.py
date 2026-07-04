"""Weight-apply operators — Add, Scale, Smooth, Sharpen + preset menus + preset setter."""

import bpy
from ...interface.utils.op_exec import run_domain_via_unified
from .weight_apply_feature import get_prefs


class OBJECT_OT_mw_add_weight(bpy.types.Operator):
    bl_idname = "object.mw_add_weight"
    bl_label = "Add Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "weight_apply", "add")


class OBJECT_OT_mw_scale_weight(bpy.types.Operator):
    bl_idname = "object.mw_scale_weight"
    bl_label = "Scale Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "weight_apply", "scale")


class OBJECT_OT_mw_smooth_weight(bpy.types.Operator):
    bl_idname = "object.mw_smooth_weight"
    bl_label = "Smooth Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "weight_apply", "smooth")


class OBJECT_OT_mw_sharpen_weight(bpy.types.Operator):
    bl_idname = "object.mw_sharpen_weight"
    bl_label = "Sharpen Weight"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return run_domain_via_unified(context, "weight_apply", "sharpen")


# ── Gesture shortcut (Alt-click Add/Scale + Smooth/Sharpen, hold-only) ────

_GESTURE_LABELS = {
    "add": "Add Weight",
    "scale": "Scale Weight",
    "smooth": "Smooth Weight",
    "sharpen": "Sharpen Weight",
}

_GESTURE_DRAG_THRESHOLD = 4  # pixels before a click becomes a drag (matches bone_picker's overlay-size gesture)
_GESTURE_DRAG_SENSITIVITY = 1.0 / 300.0  # 300px horizontal drag spans 0 -> +-1.0

# Each combined gesture's `action` property spans a signed [-1.0, 1.0] drag
# value starting at 0.0. The sign picks which of its two real domain actions
# runs; the magnitude becomes that action's intensity:
#   add_scale:       [0, 1] -> add(v)         [-1, 0] -> scale(1.0 + v)
#   smooth_sharpen:  [0, 1] -> smooth(v)      [-1, 0] -> sharpen(-v)
# So dragging left from 0 ramps scale's intensity down from 1.0 (no change)
# to 0.0 (fully scaled to zero) at -1.0, and ramps sharpen's intensity up
# from 0.0 (no change) to 1.0 at -1.0 -- both read as "0 is neutral" in
# their own direction.
_COMBINED_RESOLVERS = {
    "add_scale": (("add", lambda v: v), ("scale", lambda v: 1.0 + v)),
    "smooth_sharpen": (("smooth", lambda v: v), ("sharpen", lambda v: -v)),
}


class SUPERSKIN_OT_weight_gesture(bpy.types.Operator):
    """Alt-click hold-and-drag gesture combining two weight actions per mouse
    button, mapped onto a single signed [-1.0, 1.0] axis starting at 0.0:

      Alt+LMB (`add_scale`):      positive -> Add,    negative -> Scale
      Alt+RMB (`smooth_sharpen`): positive -> Smooth,  negative -> Sharpen

    There is no plain-click apply -- a click that never crosses the drag
    threshold does nothing at all (0.0 is neutral for both sides, so this
    also matches what a 0-intensity apply would have done, but skips the
    write/undo-step entirely instead of committing a no-op). Holding and
    dragging horizontally live-previews the resolved action/intensity on the
    mesh; releasing commits the final value as a single write (one undo
    step). There is no mid-gesture cancel by design -- the only way back is
    Blender's native Ctrl+Z, never an ESC/cancel branch here.
    """
    bl_idname = "superskin.weight_gesture"
    bl_label = "Weight Gesture"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.StringProperty(default="add_scale")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def _resolve(self, drag_value):
        """Map this gesture's signed drag value to a (real_action, intensity) pair."""
        positive, negative = _COMBINED_RESOLVERS[self.action]
        real_action, fn = positive if drag_value >= 0.0 else negative
        return real_action, fn(drag_value)

    def invoke(self, context, event):
        from ...core.facade import CoreFacade
        from .weight_apply_feature import WeightApplyFeature

        self._facade = CoreFacade(context)
        self._feature = WeightApplyFeature()
        self._ctx = self._feature.snapshot_context(self._facade)

        # add_scale needs an active bone on both sides (add and scale alike);
        # smooth_sharpen doesn't -- smooth has no active-bone requirement, and
        # sharpen's own per-call check in apply_action() already no-ops
        # safely if there's no active bone when the drag crosses negative.
        if self.action == "add_scale" and not self._ctx["is_mask"] and self._ctx["active_vg_id"] is None:
            return {'CANCELLED'}

        self._trigger_type = event.type
        self._initial_x = event.mouse_x
        self._initial_y = event.mouse_y
        self._is_dragging = False
        self._drag_value = 0.0

        context.window.cursor_modal_set('NONE')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _apply(self, context, drag_value):
        """Resolve `drag_value` to a real action/intensity and run one
        apply_action() pass, wrapped in the same superskin_internal_transaction
        guard every other weight-mutating operator uses (see
        interface/utils/op_exec.py:run_domain_via_unified)."""
        real_action, intensity = self._resolve(drag_value)
        context.scene.superskin_internal_transaction = True
        try:
            self._feature.apply_action(real_action, self._facade, self._ctx, intensity)
        finally:
            context.scene.superskin_internal_transaction = False
        return real_action, intensity

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            delta = event.mouse_x - self._initial_x
            if not self._is_dragging and abs(delta) > _GESTURE_DRAG_THRESHOLD:
                self._is_dragging = True
            if self._is_dragging:
                # `cursor_warp` below resets the mouse back to _initial_x every
                # frame (infinite-drag), so `delta` here is only the small
                # movement since the last warp -- it must be ACCUMULATED onto
                # the running value, not used as an absolute offset each time
                # (that was the bug: recomputing `delta * sensitivity` fresh
                # every frame capped the value at whatever a single event's
                # movement could reach, ~0.03-0.04).
                self._drag_value = max(-1.0, min(1.0, self._drag_value + delta * _GESTURE_DRAG_SENSITIVITY))
                real_action, intensity = self._apply(context, self._drag_value)
                context.area.header_text_set(
                    f"{_GESTURE_LABELS.get(real_action, real_action)}: {intensity:.2f}"
                )
                context.window.cursor_warp(self._initial_x, self._initial_y)

        elif event.type == self._trigger_type and event.value == 'RELEASE':
            context.window.cursor_modal_restore()
            context.area.header_text_set(None)
            if not self._is_dragging:
                # Plain click, never dragged -- no single-click apply anymore,
                # so this is a pure no-op (no write, no undo step).
                return {'CANCELLED'}
            self._apply(context, self._drag_value)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}


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
    SUPERSKIN_OT_weight_gesture,
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
