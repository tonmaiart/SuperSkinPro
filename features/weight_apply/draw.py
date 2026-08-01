"""Weight Apply gesture HUD -- horizontal drag-axis line + operation/value
readout, drawn only while SUPERSKIN_OT_weight_gesture's modal Alt-drag is
active (ops.py calls show()/update()/hide() around its own invoke/modal/
release lifecycle -- there is no persistent draw handler here, unlike
bone_picker/deform_overlay.py's always-on overlay).

Anchored to the bottom-center of the viewport region (recomputed from
`context.region` every draw, so it stays centered through a resize) rather
than tracking the cursor -- same bottom-center placement convention as
bone_picker/deform_overlay.py's "BONE PICKER" HUD and
overlay_color/multi_color_draw.py's "MULTI COLOR MODE" HUD.

Same GPU draw conventions as those: UNIFORM_COLOR shader, batch_for_shader,
POST_PIXEL on SpaceView3D. Everything is drawn in plain white (varying only
in opacity/line-width for hierarchy) rather than color-coded per action --
sizes are hardcoded, no user-facing configuration.
"""

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

_draw_handle = None

_active = False             # True while the gesture's modal is running, False otherwise
_pair_action = "add_scale"  # "add_scale" or "smooth_sharpen" -- selects the visual range below
_real_action = ""           # "add"/"scale"/"smooth"/"sharpen" -- selects the label
_intensity = 0.0
_drag_value = 0.0
_slow_tier = 0
_fine_mode = False   # True while Ctrl is held (fine sub-grid mode) -- see ops.py's _FINE_MODE_DIVISOR
_fine_anchor = 0.0   # coarse-grid value the fine sub-grid is currently centered on

_LINE_HALF_LENGTH = 150.0  # pixels each side of center -- matches ops.py's 300px-per-unit drag sensitivity at normal speed
_TICK_HEIGHT = 8.0
_END_TICK_HEIGHT = 12.0
_LINE_Y_OFFSET = 60.0   # pixels above the bottom of the region
_TEXT_MARGIN = 22.0     # pixels above the line

# How many `drag_value` units the line's full half-length represents.
# add_scale is hard-clamped to [-1, 1] in ops.py already, so 1.0 fills the
# line exactly. smooth_sharpen is deliberately unclamped -- 2.0 keeps the
# common single-gesture range legible before the marker pegs at the end
# with the overflow chevron below.
_VISUAL_RANGE = {
    "add_scale": 1.0,
    "smooth_sharpen": 2.0,
}

_LINE_COLOR = (1.0, 1.0, 1.0, 0.35)
_TICK_COLOR = (1.0, 1.0, 1.0, 0.6)
_MARKER_COLOR = (1.0, 1.0, 1.0, 1.0)
_TEXT_COLOR = (1.0, 1.0, 1.0, 1.0)

# Grid "stop" tick marks along the axis, one per step, so the drag reads as
# discrete stops rather than a bare continuous line -- `_drag_value` itself
# is now the already-quantized value ops.py applies (see update()'s
# docstring), so the marker/fill-bar above naturally jump stop-to-stop too,
# with no extra snapping logic needed here. Kept as separate constants
# (not imported from ops.py) to avoid a circular import -- ops.py already
# imports this module -- so keep these in sync with ops.py's own
# `_GRID_COARSE_STEP`/`_GRID_FINE_STEP`/`_GRID_FINE_HALF_RANGE` if they change.
_GRID_COARSE_STEP = 0.05
_GRID_FINE_STEP = 0.001
_GRID_FINE_HALF_RANGE = 0.05
_STOP_TICK_HEIGHT = 5.0
_STOP_TICK_COLOR = (1.0, 1.0, 1.0, 0.28)
_FINE_STOP_TICK_HEIGHT = 7.0
_FINE_STOP_TICK_COLOR = (1.0, 1.0, 1.0, 0.55)
# Caps how many fine sub-grid ticks are actually DRAWN, independent of
# _GRID_FINE_STEP's real snap precision -- with a step as fine as 0.001 and
# a +/-0.05 window, the real grid has 101 buckets, which would blur into a
# solid smear on a ~300px line. Every tick actually drawn still sits on a
# real, exactly-snappable value (a sparser sample of them, at a stride
# computed below), so this only thins the DISPLAY, never the precision.
_MAX_FINE_TICKS_DRAWN = 20

_GESTURE_LABELS = {
    "add": "Add Weight",
    "scale": "Scale Weight",
    "smooth": "Smooth Weight",
    "sharpen": "Sharpen Weight",
}


def _draw_text_centered(cx, y, text, color):
    font_id = 0
    blf.size(font_id, 16)
    text_w, _ = blf.dimensions(font_id, text)
    x = cx - text_w / 2.0
    blf.position(font_id, x + 1, y - 1, 0)
    blf.color(font_id, 0.0, 0.0, 0.0, 0.85)
    blf.draw(font_id, text)
    blf.position(font_id, x, y, 0)
    blf.color(font_id, *color)
    blf.draw(font_id, text)


def _draw_callback():
    if not _active:
        return
    region = bpy.context.region
    if not region:
        return
    cx, cy = region.width / 2.0, _LINE_Y_OFFSET

    visual_range = _VISUAL_RANGE.get(_pair_action, 1.0)
    # While Ctrl is held, the axis "zooms": its mapped start/end move from
    # the full [-visual_range, visual_range] span to a narrow window
    # centered on the fine anchor, +/- _GRID_FINE_HALF_RANGE (exactly one
    # coarse step each side) -- like sliding the bar's start/end in to
    # bracket the current value, so the fine sub-grid stops spread out
    # across the WHOLE visible line instead of being crammed into a sliver
    # of it. `window_center` maps to the line's exact horizontal center
    # (ratio 0) either way, so the fill bar below needs no special-casing.
    if _fine_mode:
        window_center, window_half = _fine_anchor, _GRID_FINE_HALF_RANGE
    else:
        window_center, window_half = 0.0, visual_range

    def _value_ratio(value):
        return (value - window_center) / window_half if window_half else 0.0

    raw_ratio = _value_ratio(_drag_value)
    ratio = max(-1.0, min(1.0, raw_ratio))
    marker_x = cx + ratio * _LINE_HALF_LENGTH

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    gpu.state.blend_set('ALPHA')

    # Baseline (full drag-axis extent)
    gpu.state.line_width_set(2.0)
    shader.uniform_float("color", _LINE_COLOR)
    batch_for_shader(shader, 'LINES', {"pos": [
        (cx - _LINE_HALF_LENGTH, cy), (cx + _LINE_HALF_LENGTH, cy),
    ]}).draw(shader)

    # Zero tick -- only drawn if 0.0 actually falls within the current
    # window (always true in coarse mode; only true in fine mode if the
    # zoomed-in window happens to straddle zero) -- + end ticks, which
    # always sit at the window's own boundaries (the full range in coarse
    # mode, or anchor +/- _GRID_FINE_HALF_RANGE once zoomed).
    shader.uniform_float("color", _TICK_COLOR)
    tick_pos = [
        (cx - _LINE_HALF_LENGTH, cy - _END_TICK_HEIGHT / 2), (cx - _LINE_HALF_LENGTH, cy + _END_TICK_HEIGHT / 2),
        (cx + _LINE_HALF_LENGTH, cy - _END_TICK_HEIGHT / 2), (cx + _LINE_HALF_LENGTH, cy + _END_TICK_HEIGHT / 2),
    ]
    zero_ratio = _value_ratio(0.0)
    if -1.0 <= zero_ratio <= 1.0:
        zero_x = cx + zero_ratio * _LINE_HALF_LENGTH
        tick_pos += [(zero_x, cy - _TICK_HEIGHT), (zero_x, cy + _TICK_HEIGHT)]
    batch_for_shader(shader, 'LINES', {"pos": tick_pos}).draw(shader)

    # Coarse grid stop ticks -- one small mark per _GRID_COARSE_STEP within
    # the visible window. Skipped entirely once zoomed (fine mode) -- at
    # that zoom level the only coarse-aligned positions left in view are the
    # window's own two ends, already drawn as the taller end ticks above.
    if not _fine_mode:
        n_coarse = round(visual_range / _GRID_COARSE_STEP)
        stop_pos = []
        for step in range(-n_coarse, n_coarse + 1):
            if step == 0 or abs(step) == n_coarse:
                continue
            value = step * _GRID_COARSE_STEP
            x = cx + _value_ratio(value) * _LINE_HALF_LENGTH
            stop_pos.append((x, cy - _STOP_TICK_HEIGHT))
            stop_pos.append((x, cy + _STOP_TICK_HEIGHT))
        if stop_pos:
            shader.uniform_float("color", _STOP_TICK_COLOR)
            batch_for_shader(shader, 'LINES', {"pos": stop_pos}).draw(shader)

    # Fine sub-grid stop ticks -- only while Ctrl is held. With the zoom
    # above, `i` spans the window's own +/-half_span exactly, so these would
    # spread evenly across the FULL visible line instead of a cramped sliver
    # of the full (unzoomed) range -- except `half_span` can be far larger
    # than what's legible to actually draw (see _MAX_FINE_TICKS_DRAWN), so
    # only every `stride`-th real bucket is drawn, sparsely sampling the
    # true grid rather than approximating it.
    if _fine_mode:
        half_span = round(_GRID_FINE_HALF_RANGE / _GRID_FINE_STEP)
        stride = max(1, round(half_span / max(1, _MAX_FINE_TICKS_DRAWN // 2)))
        fine_pos = []
        for i in range(-half_span, half_span + 1, stride):
            value = _fine_anchor + i * _GRID_FINE_STEP
            x = cx + _value_ratio(value) * _LINE_HALF_LENGTH
            fine_pos.append((x, cy - _FINE_STOP_TICK_HEIGHT))
            fine_pos.append((x, cy + _FINE_STOP_TICK_HEIGHT))
        # `range()` stepping by `stride` from -half_span may not land exactly
        # on +half_span -- always include the window's own boundary tick too
        # so the display stays symmetric.
        if half_span % stride != 0:
            value = _fine_anchor + half_span * _GRID_FINE_STEP
            x = cx + _value_ratio(value) * _LINE_HALF_LENGTH
            fine_pos.append((x, cy - _FINE_STOP_TICK_HEIGHT))
            fine_pos.append((x, cy + _FINE_STOP_TICK_HEIGHT))
        if fine_pos:
            shader.uniform_float("color", _FINE_STOP_TICK_COLOR)
            batch_for_shader(shader, 'LINES', {"pos": fine_pos}).draw(shader)

    # Fill bar from the window's own center (zero in coarse mode, the fine
    # anchor once zoomed -- either way this is always exactly `cx`, since
    # `window_center` maps to ratio 0 by construction) to the current value
    gpu.state.line_width_set(4.0)
    shader.uniform_float("color", _MARKER_COLOR)
    batch_for_shader(shader, 'LINES', {"pos": [(cx, cy), (marker_x, cy)]}).draw(shader)

    # Marker at the current position
    gpu.state.line_width_set(1.0)
    marker_half = _TICK_HEIGHT * 0.9
    batch_for_shader(shader, 'LINES', {"pos": [
        (marker_x, cy - marker_half), (marker_x, cy + marker_half),
    ]}).draw(shader)

    # Overflow chevron -- the real (unclamped) value has run past what the
    # CURRENT window can show: the full range in coarse mode (smooth_sharpen
    # only; add_scale is hard-clamped so this never fires for it there), or
    # the zoomed fine window once Ctrl is held and the drag has moved beyond
    # its anchor +/- _GRID_FINE_HALF_RANGE.
    if abs(raw_ratio) > 1.0:
        chevron_dir = 1.0 if raw_ratio > 0 else -1.0
        tip_x = marker_x + chevron_dir * 6.0
        batch_for_shader(shader, 'LINES', {"pos": [
            (marker_x, cy - marker_half), (tip_x, cy),
            (tip_x, cy), (marker_x, cy + marker_half),
        ]}).draw(shader)

    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')

    # Fine mode overrides the slow-tier divisor entirely (see ops.py's
    # _FINE_MODE_DIVISOR) rather than stacking with it, so its suffix
    # replaces -- not appends to -- the [Slow xN] one.
    if _fine_mode:
        mode_suffix = f"  [Fine ±{_GRID_FINE_HALF_RANGE:.2f} @{_fine_anchor:.2f}]"
    elif _slow_tier:
        mode_suffix = f"  [Slow x{_slow_tier}]"
    else:
        mode_suffix = ""
    label = _GESTURE_LABELS.get(_real_action, _real_action or "Weight Apply")
    _draw_text_centered(cx, cy + _TEXT_MARGIN, f"{label}: {_intensity:.2f}{mode_suffix}", _TEXT_COLOR)


def show(pair_action):
    """Install the draw handler and pin the gesture's fixed pair -- called
    once from ops.py's invoke(), before any drag has actually started
    (values default to the neutral 0.0 state until the first update()
    call)."""
    global _draw_handle, _active, _pair_action, _real_action, _intensity, _drag_value, _slow_tier
    global _fine_mode, _fine_anchor
    _active = True
    _pair_action = pair_action
    _real_action = ""
    _intensity = 0.0
    _drag_value = 0.0
    _slow_tier = 0
    _fine_mode = False
    _fine_anchor = 0.0
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_callback, (), 'WINDOW', 'POST_PIXEL')
    _tag_redraw()


def update(real_action, intensity, drag_value, slow_tier, fine_mode=False, fine_anchor=None):
    """Refresh the live readout -- called from ops.py's modal() on every
    MOUSEMOVE (cheap: pure Python + tag_redraw, no FFI call) so the marker
    and text track the drag in real time, independent of the throttled
    TIMER tick that actually applies the weight change.

    `drag_value` is ops.py's already-QUANTIZED grid value (`current_idx /
    _grid_n(fine_mode)`, matching exactly what `modal()`'s TIMER branch
    applies), not the raw continuous drag position -- this is what makes the
    marker/fill-bar in `_draw_callback` jump stop-to-stop instead of
    tracking the mouse smoothly, matching the stop tick marks drawn along
    the axis.

    `fine_mode`/`fine_anchor` reflect ops.py's Ctrl-held fine sub-grid state
    (default args keep this call signature-compatible with any other
    caller) -- see `_draw_callback`'s suffix composition above."""
    global _real_action, _intensity, _drag_value, _slow_tier, _fine_mode, _fine_anchor
    _real_action = real_action
    _intensity = intensity
    _drag_value = drag_value
    _slow_tier = slow_tier
    _fine_mode = fine_mode
    if fine_anchor is not None:
        _fine_anchor = fine_anchor
    _tag_redraw()


def hide():
    global _draw_handle, _active
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    _active = False
    _tag_redraw()


def cleanup():
    """Defensive unregister-time cleanup -- guards against an F3 script
    reload landing mid-gesture and leaving a dangling draw handle behind."""
    hide()


def _tag_redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
