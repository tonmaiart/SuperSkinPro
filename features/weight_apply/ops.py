"""Weight-apply operators — Add, Scale, Smooth, Sharpen + preset menus + preset setter."""

import bpy
from ...core.facade import CoreFacade
from ...interface.utils.op_exec import run_domain_via_unified
from .weight_apply_feature import get_prefs


class OBJECT_OT_mw_add_weight(bpy.types.Operator):
    bl_idname = "object.mw_add_weight"
    bl_label = "Add Weight"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return CoreFacade.is_system_activated() and CoreFacade.is_editing_weights()

    def execute(self, context):
        return run_domain_via_unified(context, "weight_apply", "add")


class OBJECT_OT_mw_scale_weight(bpy.types.Operator):
    bl_idname = "object.mw_scale_weight"
    bl_label = "Scale Weight"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return CoreFacade.is_system_activated() and CoreFacade.is_editing_weights()

    def execute(self, context):
        return run_domain_via_unified(context, "weight_apply", "scale")


class OBJECT_OT_mw_smooth_weight(bpy.types.Operator):
    bl_idname = "object.mw_smooth_weight"
    bl_label = "Smooth Weight"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return CoreFacade.is_system_activated() and CoreFacade.is_editing_weights()

    def execute(self, context):
        return run_domain_via_unified(context, "weight_apply", "smooth")


class OBJECT_OT_mw_sharpen_weight(bpy.types.Operator):
    bl_idname = "object.mw_sharpen_weight"
    bl_label = "Sharpen Weight"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return CoreFacade.is_system_activated() and CoreFacade.is_editing_weights()

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
# Scroll-down during the gesture steps through these divisors in order
# (index 0 = normal speed); scroll-up steps back down toward index 0.
_GESTURE_SLOW_DIVISORS = (1.0, 3.0, 6.0)
_GESTURE_APPLY_INTERVAL = 1.0 / 60.0  # cap expensive apply+flatten ticks to ~60Hz, independent of raw MOUSEMOVE rate
# Was 1/30 (~9ms measured compute in a 33ms budget, 27% duty cycle) -- after
# the dirty_verts/caching optimizations landed, there's enough headroom to
# double the tick rate (~54% duty cycle at 60Hz) for a smoother feel without
# meaningfully raising CPU cost. Lower this back toward 1/30-1/20 if a much
# larger/heavier scene pushes per-tick compute closer to the new budget.

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
    """Hold-and-drag gesture combining two pairs of weight actions, mapped
    onto a single signed drag axis starting at 0.0:

      Alt+LMB (`add_scale`):        positive -> Add,     negative -> Scale
      Alt+Shift+LMB (`smooth_sharpen`): positive -> Smooth, negative -> Sharpen

    Each keymap entry starts the gesture directly in its own fixed mode --
    there is no mid-gesture mode switch (a previous revision had a Ctrl-tap
    toggle between the two; that has been removed, so `self.action` is the
    mode for the whole gesture, not just its starting point).

    There is no plain-click apply -- a click that never crosses the drag
    threshold does nothing at all (0.0 is neutral for both sides, so this
    also matches what a 0-intensity apply would have done, but skips the
    write/undo-step entirely instead of committing a no-op). Holding and
    dragging horizontally live-previews the resolved action/intensity on the
    mesh; releasing commits the final value as a single write (one undo
    step). There is no mid-gesture cancel by design -- the only way back is
    Blender's native Ctrl+Z, never an ESC/cancel branch here.

    `add_scale`'s drag value stays clamped to [-1.0, 1.0] (Add/Scale's
    intensity is meaningful only in that range), but `smooth_sharpen`'s is
    deliberately left unclamped so repeated/larger drags can smooth or
    sharpen further than a single clamped pass would allow.

    Scrolling during the drag steps through `_GESTURE_SLOW_DIVISORS`:
    scroll down moves to the next (slower) tier -- normal -> 3x slower ->
    6x slower, capped there -- scroll up steps back toward normal. This
    replaced a previous Shift-tap on/off toggle with a genuine two-level
    slow-down, addressable in either direction.

    MOUSEMOVE can fire far faster than the expensive apply+flatten path can
    usefully keep up with (100+ Hz on some mice/tablets), so tracking the
    drag value is decoupled from actually applying it: MOUSEMOVE only updates
    `self._drag_value` (cheap arithmetic), and a modal TIMER event
    (`_GESTURE_APPLY_INTERVAL`) is what actually triggers `_apply()`. This
    bounds apply+flatten calls/sec to a fixed budget regardless of raw input
    rate. RELEASE always applies once more unconditionally so the committed
    result matches the last-seen mouse position exactly, even if it lands
    between two timer ticks.

    RELEASE commits by writing the final drag value into the `drag_value`
    RNA property and calling `self.execute()` (rather than duplicating the
    apply logic inline), which is what makes this operator show Blender's
    native "Adjust Last Operation" panel (bottom-left, F9) afterward --
    dragging that panel's "Amount" slider re-resolves and re-applies from a
    fresh baseline exactly like any other native redo-able tool. See
    `_ensure_baseline()` for why `execute()` must work both right after the
    modal ends (same instance, baseline already snapshotted at invoke) and
    when redo constructs a brand-new instance with no modal history.
    """
    bl_idname = "superskin.weight_gesture"
    bl_label = "Weight Gesture"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.StringProperty(default="add_scale", options={'HIDDEN'})
    drag_value: bpy.props.FloatProperty(
        name="Amount",
        description=(
            "Resolved gesture drag value. Meaning depends on this gesture's "
            "mode: add_scale maps [0, 1] -> Add and [-1, 0] -> Scale; "
            "smooth_sharpen maps [0, 1] -> Smooth and [-1, 0] -> Sharpen "
            "(unclamped beyond that range)"
        ),
        default=0.0, soft_min=-1.0, soft_max=1.0,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (CoreFacade.is_system_activated() and CoreFacade.is_editing_weights() and
                obj is not None and obj.type == 'MESH')

    def _resolve(self, drag_value):
        """Map this gesture's signed drag value to a (real_action, intensity) pair."""
        if self.action == "add_scale":
            drag_value = max(-1.0, min(1.0, drag_value))
        positive, negative = _COMBINED_RESOLVERS[self.action]
        real_action, fn = positive if drag_value >= 0.0 else negative
        return real_action, fn(drag_value)

    def _ensure_baseline(self, context):
        """Lazily build the facade/feature/snapshot baseline `_apply()` and
        `execute()` compute from. Already set by `invoke()` for the instance
        that ran the modal gesture -- this only matters for the *separate*
        operator instance Blender's redo panel constructs to call
        `execute()` directly (no invoke/modal), which needs its own fresh
        snapshot taken from the current (by then already undone-back-to-
        pre-gesture) context."""
        if getattr(self, "_facade", None) is None:
            from ...core.facade import CoreFacade
            from .weight_apply_feature import WeightApplyFeature
            self._facade = CoreFacade(context)
            self._feature = WeightApplyFeature()
            self._ctx = self._feature.snapshot_context(self._facade)
        return self._facade, self._feature, self._ctx

    def execute(self, context):
        """Resolve `self.drag_value` against `self.action` and apply once.
        Called directly for the modal's own final RELEASE commit, and by
        Blender's redo panel (with `drag_value` possibly tweaked) after it
        undoes the previous commit -- both paths must reproduce identically
        from a fresh baseline, so this never reads modal-only state like
        `self._is_dragging`."""
        facade, feature, ctx = self._ensure_baseline(context)
        real_action, intensity = self._resolve(self.drag_value)
        context.scene.superskin_internal_transaction = True
        try:
            result = feature.apply_action(real_action, facade, ctx, intensity)
        finally:
            context.scene.superskin_internal_transaction = False
        if result.get("status") == "CANCELLED":
            return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        self._ensure_baseline(context)

        self._trigger_type = event.type
        self._initial_x = event.mouse_x
        self._initial_y = event.mouse_y
        self._is_dragging = False
        self._drag_value = 0.0
        self._last_applied_value = None
        self._slow_tier = 0

        context.window.cursor_modal_set('NONE')
        self._timer = context.window_manager.event_timer_add(
            _GESTURE_APPLY_INTERVAL, window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _remove_timer(self, context):
        context.window_manager.event_timer_remove(self._timer)

    def _apply(self, context, drag_value):
        """Resolve `drag_value` to a real action/intensity and run one
        apply_action() pass, wrapped in the same superskin_internal_transaction
        guard every other weight-mutating operator uses (see
        interface/utils/op_exec.py:run_domain_via_unified).

        No active-bone gate here -- `apply_action()` itself already no-ops
        gracefully (returns a CANCELLED-status dict, no write) for
        add/scale/sharpen with no active bone and no mask context; Smooth
        never needed one. Gating at invoke() would have blocked the whole
        gesture whenever it started in add_scale mode with nothing selected."""
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
                # NOTE: only the value is tracked here -- the expensive
                # apply+flatten call is throttled to the TIMER tick below, not
                # run on every MOUSEMOVE (see class docstring).
                sensitivity = _GESTURE_DRAG_SENSITIVITY / _GESTURE_SLOW_DIVISORS[self._slow_tier]
                new_value = self._drag_value + delta * sensitivity
                if self.action == "add_scale":
                    new_value = max(-1.0, min(1.0, new_value))
                self._drag_value = new_value
                context.window.cursor_warp(self._initial_x, self._initial_y)

        elif event.type == 'WHEELDOWNMOUSE':
            # Step to the next (slower) tier, capped at the last one.
            self._slow_tier = min(self._slow_tier + 1, len(_GESTURE_SLOW_DIVISORS) - 1)
            return {'RUNNING_MODAL'}

        elif event.type == 'WHEELUPMOUSE':
            # Step back toward normal speed, capped at 0.
            self._slow_tier = max(self._slow_tier - 1, 0)
            return {'RUNNING_MODAL'}

        elif event.type == 'TIMER':
            if self._is_dragging and self._drag_value != self._last_applied_value:
                real_action, intensity = self._apply(context, self._drag_value)
                self._last_applied_value = self._drag_value
                slow_suffix = (
                    f" [Slow x{_GESTURE_SLOW_DIVISORS[self._slow_tier]:.0f}]"
                    if self._slow_tier > 0 else ""
                )
                context.area.header_text_set(
                    f"{_GESTURE_LABELS.get(real_action, real_action)}: {intensity:.2f}"
                    + slow_suffix
                )

        elif event.type == self._trigger_type and event.value == 'RELEASE':
            self._remove_timer(context)
            context.window.cursor_modal_restore()
            context.area.header_text_set(None)
            if not self._is_dragging:
                # Plain click, never dragged -- no single-click apply anymore,
                # so this is a pure no-op (no write, no undo step).
                return {'CANCELLED'}
            # Always apply once more unconditionally, even if _drag_value
            # already matches _last_applied_value -- guarantees the committed
            # result matches the last-seen mouse position exactly, regardless
            # of where release lands relative to the last timer tick.
            # Routed through execute() (not _apply() directly) so the RNA
            # `drag_value` property reflects the committed value -- that's
            # what Blender's redo panel reads/writes on a later re-execute.
            self.drag_value = self._drag_value
            return self.execute(context)

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
