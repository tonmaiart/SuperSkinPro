"""Deform Bone Skeleton Overlay — persistent wedge-skeleton in Edit Mode.

Owned by the bone_picker feature package.  draw_handler_add with POST_PIXEL
always renders on top of ShaderManager's POST_VIEW weight colors.

Colors and wedge width are read from ``superskin_bone_picker_prefs``
(static_active_color / static_multi_color / static_default_color /
static_wedge_width).  Hardcoded tuples below serve as fallback only.

Bug fixes:
- LINE_LOOP removed in Blender 5.0 → LINE_STRIP with closed vertex list.
- batch_for_shader in Blender 5.0 requires plain tuples, not Vector objects.
- Removed depsgraph auto-hide handler: it fired immediately after show() on
  every depsgraph update (including the one from the toggle operator itself)
  and called hide() again before the first frame rendered.  The draw callback
  guards itself with obj.mode != 'EDIT' so it simply draws nothing when not
  in Edit Mode — no separate hide mechanism needed.
"""

import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils
from mathutils import Vector

_draw_handle = None
_hovered_bone: str | None = None
_is_holding: bool = False

# Fallback constants (used when prefs are unavailable)
_HEAD_HALF_WIDTH   = 5.0
_COLOR_DEFAULT     = (0.35, 0.65, 1.0, 0.35)
_COLOR_MULTI       = (0.0,  0.3,  0.75, 0.9)
_COLOR_ACTIVE      = (1.0,  0.15, 0.15, 1.0)


def _get_static_prefs():
    """Return (active_color, multi_color, default_color, hover_color, wedge_width, line_width,
    hover_extra, hold_extra, overall_size, pivot_ratio, fill_opacity, head_circle_size)."""
    try:
        bp = bpy.context.window_manager.superskin_bone_picker_prefs
        return (
            tuple(bp.static_active_color),
            tuple(bp.static_multi_color),
            tuple(bp.static_default_color),
            tuple(bp.hover_color),
            bp.static_wedge_width,
            bp.static_line_width,
            bp.hover_line_width,
            bp.hold_line_width,
            bp.overall_size,
            bp.pivot_ratio,
            bp.fill_opacity,
            bp.head_circle_size,
        )
    except Exception:
        return _COLOR_ACTIVE, _COLOR_MULTI, _COLOR_DEFAULT, (1.0, 0.55, 0.0, 1.0), _HEAD_HALF_WIDTH, 1, 2, 3, 1.0, 0.333, 0.25, 0.55


def _draw_filled_circle(shader, center, radius, fill_color, outline_color, segments=16):
    cx, cy = center
    verts = [(cx, cy)]
    for i in range(segments):
        a = (2 * math.pi * i) / segments
        verts.append((cx + math.cos(a) * radius, cy + math.sin(a) * radius))
    indices = [(0, i + 1, (i + 1) % segments + 1) for i in range(segments)]
    shader.uniform_float("color", fill_color)
    batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=indices).draw(shader)
    outline_verts = list(verts[1:]) + [verts[1]]
    shader.uniform_float("color", outline_color)
    batch_for_shader(shader, 'LINE_STRIP', {"pos": outline_verts}).draw(shader)


def _draw_bone_rhombus(shader, head_2d, tail_2d, fill_color, outline_color, half_width, pivot_ratio=0.333):
    direction = tail_2d - head_2d
    length = direction.length
    if length < 0.0001:
        return
    direction_n = direction.normalized()
    perp = Vector((-direction_n.y, direction_n.x)) * half_width

    pivot = head_2d + direction_n * (length * pivot_ratio)
    h  = tuple(head_2d)
    pl = tuple(pivot + perp)
    pr = tuple(pivot - perp)
    t  = tuple(tail_2d)

    shader.uniform_float("color", fill_color)
    batch_for_shader(shader, 'TRIS', {"pos": [h, pl, t, pr]},
                     indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)

    shader.uniform_float("color", outline_color)
    batch_for_shader(shader, 'LINE_STRIP', {"pos": [h, pl, t, pr, h]}).draw(shader)


def _draw_callback():
    context = bpy.context
    obj = context.active_object
    # Self-silencing: draw nothing outside Edit Mode.  No separate hide needed.
    if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
        return

    region = context.region
    rv3d   = context.region_data
    if not region or not rv3d:
        return

    armature = next((m.object for m in obj.modifiers if m.type == 'ARMATURE'), None)
    if not armature:
        return

    vg_names     = {vg.name for vg in obj.vertex_groups}
    deform_bones = {b.name for b in armature.data.bones if b.use_deform}

    storage     = getattr(obj, "superskin_storage", None)
    active_idx  = getattr(storage, "last_clicked_index", -1) if storage else -1
    active_name = None
    if 0 <= active_idx < len(obj.vertex_groups):
        active_name = obj.vertex_groups[active_idx].name
    selected_names = getattr(storage, "selected_names", "") if storage else ""

    (color_active, color_multi, color_default, color_hover,
     wedge_width, line_width, hover_extra, hold_extra,
     overall_size, pivot_ratio, fill_opacity, head_circle_size) = _get_static_prefs()

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    gpu.state.blend_set('ALPHA')

    for bone in armature.pose.bones:
        if bone.name not in deform_bones or bone.name not in vg_names:
            continue

        head_3d = armature.matrix_world @ bone.head
        tail_3d = armature.matrix_world @ bone.tail

        head_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, head_3d)
        tail_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, tail_3d)
        if head_2d is None or tail_2d is None:
            continue

        is_active  = (bone.name == active_name)
        is_in_pool = f",{bone.name}," in selected_names
        is_hovered = (bone.name == _hovered_bone)
        if is_hovered:
            color = color_hover
        elif is_active:
            color = color_active
        elif is_in_pool:
            color = color_multi
        else:
            color = color_default
        w = line_width + (hover_extra if is_hovered else 0) + (hold_extra if _is_holding else 0)
        gpu.state.line_width_set(w)

        fill_color = (*color[:3], color[3] * fill_opacity)
        eff_width = wedge_width * overall_size
        head_r = eff_width * head_circle_size

        seg_dir = tail_2d - head_2d
        seg_len = seg_dir.length
        if seg_len > head_r:
            dir_n = seg_dir / seg_len
            bone_start = head_2d + dir_n * head_r
            _draw_bone_rhombus(shader, bone_start, tail_2d, fill_color, color, eff_width, pivot_ratio)

        _draw_filled_circle(shader, tuple(head_2d), head_r, fill_color, color)

    gpu.state.line_width_set(1)
    gpu.state.blend_set('NONE')


# ── Public API ────────────────────────────────────────────────────────────────

def set_hover(bone_name: str | None) -> None:
    global _hovered_bone
    _hovered_bone = bone_name


def clear_hover() -> None:
    global _hovered_bone
    _hovered_bone = None


def set_holding(state: bool) -> None:
    global _is_holding
    _is_holding = state

def show():
    global _draw_handle
    if _draw_handle is not None:
        return
    _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_callback, (), 'WINDOW', 'POST_PIXEL'
    )
    _tag_redraw()


def hide():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
        _tag_redraw()


def toggle():
    hide() if _draw_handle is not None else show()


def is_visible() -> bool:
    return _draw_handle is not None


def cleanup():
    """Called from features/bone_picker/__init__.py unregister()."""
    hide()


def _tag_redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
