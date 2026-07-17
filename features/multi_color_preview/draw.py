"""Multi-color (rainbow) per-bone weight visualizer for SuperSkinPro.

GPU draw logic extracted from core/shaders/bone_mode.py (MULTI sub-mode) and
core/shaders/visualizer_base.py.  All data access uses Blender properties
directly so this module has zero imports from core/ sub-modules.
"""

import array
import json
import time
import bpy
import bmesh
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ...interface.utils.gpu_utils import (
    GL_POLYGON_OFFSET_FILL,
    gl_polygon_offset, gl_enable, gl_disable,
    BONE_COLORS,
    get_custom_wire_shader, get_custom_point_shader,
)

_WIRE_COLOR = (0.05, 0.05, 0.05, 0.95)

# ── Module-level state ──────────────────────────────────────────────────────
_active = False
_draw_handle = None
_hud_handle = None

# _user_enabled: the user's own toggle intent, independent of temporary
# mask suppression. _suppressed_by_mask: True only when _active is False
# specifically because the watcher auto-stopped it for the mask row (not
# because the user turned it off) — see start()/stop()/_watcher_tick().
_user_enabled = False
_suppressed_by_mask = False
_watch_timer_registered = False

# ── Three-tier GPU cache ────────────────────────────────────────────────────
_topo_cache = {
    "batch_wire": None,
    "tri_indices": None,
    "coords_3d": None,
    "topo_key": None,
    "structural_key": None,
}
_sel_cache = {
    "batch_sel": None,
    "batch_unsel": None,
    "sel_key": None,
}
_col_cache = {
    "batch_col": None,
    "color_key": None,
}

# The color cache key includes the active VG (see _make_color_key) so the
# active-bone highlight updates live -- but the bone picker's hover preview
# changes the active VG on every newly-hovered bone while sweeping the mouse
# across the armature, which without a floor would re-run the full per-vertex
# blend (_compute_multi_rainbow_colors) and rebuild+re-upload the entire GPU
# color batch on every single hover change, multiple times a second. Topology
# changes (rarer, correctness-sensitive) still recompute immediately; only
# the active-VG-only case is throttled.
_MIN_COLOR_RECOMPUTE_INTERVAL = 0.08  # ~12Hz ceiling
_last_color_compute_time = 0.0

# Same idea for the full topology/coords rebuild (wire + selection-point +
# color batches, all keyed off the same extracted coords_3d). frame_current
# and __ssp_deform_gen are both included in topo_key on purpose (see
# docs/bug-history/0010 — the deform-generation counter exists specifically
# so a weight edit at a fixed frame still re-extracts deformed coordinates),
# but that means dragging the timeline slider re-triggers the single most
# expensive path (full coordinate extraction + wire/point/color GPU batch
# rebuild) on every frame step. Vert/edge/face counts changing is a genuine
# topology edit and always rebuilds immediately; a frame/deform-gen-only
# change is throttled the same way the color-only path is above.
_MIN_TOPO_RECOMPUTE_INTERVAL = 0.08  # ~12Hz ceiling
_last_topo_compute_time = 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  Data access — reads Blender properties without importing core modules
# ═══════════════════════════════════════════════════════════════════════════

def _read_active_layer(obj) -> dict:
    """Return {v_idx(int): {bone_name(str): weight(float)}} for the active layer.

    In Edit Mode reads from __ssp_* temp VGs via bmesh.
    In other modes decodes the ss_layer_N JSON property.
    """
    if obj.mode == 'EDIT':
        try:
            bm = bmesh.from_edit_mesh(obj.data)
            deform_layer = bm.verts.layers.deform.active
            if not deform_layer:
                return {}
            map_raw = obj.get("__ssp_meta_map", "{}")
            id_to_bone = {int(k): v for k, v in json.loads(map_raw).items()}
            if not id_to_bone:
                return {}
            vg_map = {vg.name: vg.index for vg in obj.vertex_groups}
            bone_to_vg = {}
            for bone_id, bone_name in id_to_bone.items():
                temp_name = f"__ssp_{bone_id}"
                if temp_name in vg_map:
                    bone_to_vg[bone_name] = vg_map[temp_name]
            result = {}
            for vert in bm.verts:
                vw = vert[deform_layer]
                weights = {bname: vw[vgi] for bname, vgi in bone_to_vg.items()
                           if vgi in vw and vw[vgi] > 0.0}
                if weights:
                    result[vert.index] = weights
            return result
        except Exception:
            return {}
    else:
        try:
            active_idx = obj.data.get("ss_active_layer", 0)
            raw = obj.data.get(f"ss_layer_{active_idx}", "")
            if not raw:
                return {}
            data = json.loads(raw)
            return {int(k): v for k, v in data.items() if v}
        except Exception:
            return {}


def _get_active_bone_name(obj) -> str:
    try:
        storage = obj.superskin_storage
        if storage.active_orphan_name:
            return storage.active_orphan_name
        idx = storage.last_clicked_index
        if 0 <= idx < len(obj.vertex_groups):
            return obj.vertex_groups[idx].name
    except Exception:
        pass
    return ""


def _extract_coords(obj_eval, num_verts):
    """Extract evaluated vertex coordinates as a flat array."""
    try:
        coords_flat = array.array("d", [0.0]) * (num_verts * 3)
        obj_eval.data.vertices.foreach_get("co", coords_flat)
        return coords_flat
    except Exception:
        pass
    try:
        mesh = obj_eval.to_mesh()
        coords_flat = array.array("d", [0.0]) * (num_verts * 3)
        for vi, v in enumerate(mesh.vertices):
            b = vi * 3
            coords_flat[b] = v.co.x
            coords_flat[b + 1] = v.co.y
            coords_flat[b + 2] = v.co.z
        obj_eval.to_mesh_clear()
        return coords_flat
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  Color computation
# ═══════════════════════════════════════════════════════════════════════════

_bone_color_map = None
_last_mesh_name = ""


def _compute_bone_colors_map(obj) -> dict:
    """Assign palette colors to bones via BFS of the armature hierarchy."""
    color_map = {}
    palette = BONE_COLORS
    n_colors = len(palette)
    if n_colors == 0:
        return color_map

    for vgroup in obj.vertex_groups:
        color_map[vgroup.name] = palette[vgroup.index % n_colors]

    arm_obj = obj.find_armature()
    if not arm_obj or not arm_obj.data:
        return color_map

    bones = arm_obj.data.bones
    visited = set()
    root_bones = [b for b in bones if b.parent is None]
    queue = []
    for i, root in enumerate(root_bones):
        queue.append((root, i % n_colors))
        visited.add(root.name)

    while queue:
        bone, color_idx = queue.pop(0)
        if bone.name in obj.vertex_groups:
            color_map[bone.name] = palette[color_idx]
        for child_idx, child in enumerate(bone.children):
            if child.name not in visited:
                visited.add(child.name)
                next_idx = (color_idx + child_idx + 1) % n_colors
                queue.append((child, next_idx))

    for item in getattr(obj, 'superskin_bones_collection', ()):
        if item.is_orphan and item.name not in color_map:
            color_map[item.name] = (1.0, 0.5, 0.0)

    return color_map


def _compute_multi_rainbow_colors(obj, num_verts) -> list:
    """Compute per-vertex RGB by blending bone colors weighted by influence."""
    global _bone_color_map, _last_mesh_name

    layer_weights = _read_active_layer(obj)
    active_vg_name = _get_active_bone_name(obj)

    if _bone_color_map is None or _last_mesh_name != obj.name:
        _bone_color_map = _compute_bone_colors_map(obj)
        _last_mesh_name = obj.name

    vert_colors = [None] * num_verts
    for v_idx in range(num_verts):
        dv = layer_weights.get(v_idx, {})
        r = g = b = total = active_weight = 0.0

        for g_name, w in dv.items():
            w = float(w)
            if w <= 0.0 or g_name not in _bone_color_map:
                continue
            cr, cg, cb = _bone_color_map[g_name]
            r += cr * w
            g += cg * w
            b += cb * w
            total += w
            if g_name == active_vg_name:
                active_weight = w

        if total <= 0.0:
            vert_colors[v_idx] = (0.0, 0.0, 0.0)
            continue
        if total > 1.0:
            inv = 1.0 / total
            r *= inv
            g *= inv
            b *= inv

        if active_vg_name and active_weight > 0.01:
            t = active_weight * 0.95
            r += (1.0 - r) * t
            g += (1.0 - g) * t
            b += (1.0 - b) * t

        vert_colors[v_idx] = (r, g, b)
    return vert_colors


# ═══════════════════════════════════════════════════════════════════════════
#  GPU batch builders
# ═══════════════════════════════════════════════════════════════════════════

def _build_topo_batches(bm, obj, coords_flat, num_verts):
    matrix = obj.matrix_world
    tris = bm.calc_loop_triangles()

    coords_3d = [None] * num_verts
    for vi in range(num_verts):
        base = vi * 3
        if base + 2 < len(coords_flat):
            v = (coords_flat[base], coords_flat[base + 1], coords_flat[base + 2])
            coords_3d[vi] = matrix @ Vector(v)

    edges = bm.edges
    if edges:
        n = len(edges) * 2
        wire = [None] * n
        for ei, e in enumerate(edges):
            base = ei * 2
            wire[base] = coords_3d[e.verts[0].index]
            wire[base + 1] = coords_3d[e.verts[1].index]
        sh = get_custom_wire_shader()
        _topo_cache["batch_wire"] = batch_for_shader(sh, 'LINES', {"pos": wire})
    else:
        _topo_cache["batch_wire"] = None

    if tris:
        tri_indices = []
        for tri in tris:
            for loop in tri:
                tri_indices.append(loop.vert.index)
        _topo_cache["tri_indices"] = tri_indices
    else:
        _topo_cache["tri_indices"] = None

    _topo_cache["coords_3d"] = coords_3d
    return coords_3d


def _build_sel_batches(bm, coords_3d, num_verts):
    verts = bm.verts
    sel_coords = [coords_3d[v.index] for v in verts if v.select]
    unsel_coords = [coords_3d[v.index] for v in verts if not v.select]
    sh = get_custom_point_shader()
    _sel_cache["batch_unsel"] = (
        batch_for_shader(sh, 'POINTS', {"pos": unsel_coords}) if unsel_coords else None)
    _sel_cache["batch_sel"] = (
        batch_for_shader(sh, 'POINTS', {"pos": sel_coords}) if sel_coords else None)


def _build_tris_color_batch(vert_colors, coords_3d):
    tris = _topo_cache.get("tri_indices")
    if tris:
        n = len(tris)
        coords_flat_out = [None] * n
        colors = [None] * n
        for ti in range(0, n, 3):
            for li in range(3):
                idx = ti + li
                vi = tris[idx]
                coords_flat_out[idx] = coords_3d[vi]
                r, g, b = vert_colors[vi] if (vi < len(vert_colors) and vert_colors[vi]) else (0.0, 0.0, 0.0)
                colors[idx] = (r, g, b, 0.98)
        sh = gpu.shader.from_builtin('SMOOTH_COLOR')
        _col_cache["batch_col"] = batch_for_shader(
            sh, 'TRIS', {"pos": coords_flat_out, "color": colors})
    else:
        _col_cache["batch_col"] = None


# ═══════════════════════════════════════════════════════════════════════════
#  Cache key builders
# ═══════════════════════════════════════════════════════════════════════════

def _make_structural_key(obj, bm):
    """Vert/edge/face counts only — a *real* topology edit (extrude, delete,
    subdivide...) always changes this and must rebuild immediately."""
    return (obj.name, id(obj.data), len(bm.verts), len(bm.edges), len(bm.faces))


def _make_topo_key(obj, bm, frame):
    return (obj.name, id(obj.data), len(bm.verts), len(bm.edges),
            len(bm.faces), frame, obj.get("__ssp_deform_gen", 0))


def _make_sel_key(obj, bm, frame):
    return (obj.name, id(obj.data),
            len(bm.select_history), obj.data.total_vert_sel, frame)


def _make_color_key(obj, bm, frame):
    try:
        active_vg_id = obj.superskin_storage.last_clicked_index
        orphan_name = obj.superskin_storage.active_orphan_name
    except Exception:
        active_vg_id = -1
        orphan_name = ""
    return (obj.name, id(obj.data),
            obj.data.get("ss_active_layer", 0),
            active_vg_id, orphan_name, frame,
            obj.get("__ssp_deform_gen", 0))


# ═══════════════════════════════════════════════════════════════════════════
#  Draw callbacks
# ═══════════════════════════════════════════════════════════════════════════

def _draw():
    context = bpy.context
    obj = context.active_object
    if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
        return

    bm = bmesh.from_edit_mesh(obj.data)
    depsgraph = context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)

    num_verts = len(bm.verts)
    frame = context.scene.frame_current

    structural_key = _make_structural_key(obj, bm)
    topo_key = _make_topo_key(obj, bm, frame)
    sel_key = _make_sel_key(obj, bm, frame)
    color_key = _make_color_key(obj, bm, frame)

    global _last_topo_compute_time
    topo_key_mismatch = (_topo_cache.get("topo_key") != topo_key)
    topo_stale = False
    if topo_key_mismatch:
        structural_stale = (_topo_cache.get("structural_key") != structural_key)
        now = time.monotonic()
        throttled = (not structural_stale) and (now - _last_topo_compute_time) < _MIN_TOPO_RECOMPUTE_INTERVAL
        # A throttled skip deliberately does NOT touch topo_key/structural_key
        # in the cache, so topo_key_mismatch stays True and the next redraw
        # re-checks — once a real topology edit happens (always bypasses the
        # throttle) or the throttle window passes, it catches up.
        topo_stale = not throttled

    sel_stale = topo_stale or (_sel_cache.get("sel_key") != sel_key)
    color_stale = topo_stale or (_col_cache.get("color_key") != color_key)

    coords_3d = None if topo_stale else _topo_cache.get("coords_3d")

    if topo_stale:
        coords_flat = _extract_coords(obj_eval, num_verts)
        if coords_flat is None:
            matrix = obj.matrix_world
            coords_flat = array.array("d", [0.0]) * (num_verts * 3)
            for vi, v in enumerate(bm.verts):
                b = vi * 3
                coords_flat[b] = v.co.x
                coords_flat[b + 1] = v.co.y
                coords_flat[b + 2] = v.co.z
        coords_3d = _build_topo_batches(bm, obj, coords_flat, num_verts)
        _topo_cache["topo_key"] = topo_key
        _topo_cache["structural_key"] = structural_key
        _last_topo_compute_time = time.monotonic()
        color_stale = True
        sel_stale = True

    if sel_stale:
        if coords_3d is None:
            coords_3d = _topo_cache.get("coords_3d")
        if coords_3d:
            _build_sel_batches(bm, coords_3d, num_verts)
            _sel_cache["sel_key"] = sel_key

    if color_stale:
        global _last_color_compute_time
        now = time.monotonic()
        # Topology changes always recompute immediately; an active-VG-only
        # change (hover during bone picking) is throttled to a ceiling rate.
        # color_key deliberately does NOT get updated on a throttled skip,
        # so color_stale stays True and the next redraw re-checks — once the
        # picker settles (or the throttle window passes), it catches up.
        throttled = (not topo_stale) and (now - _last_color_compute_time) < _MIN_COLOR_RECOMPUTE_INTERVAL
        if not throttled:
            if coords_3d is None:
                coords_3d = _topo_cache.get("coords_3d")
            if coords_3d:
                vert_colors = _compute_multi_rainbow_colors(obj, num_verts)
                _build_tris_color_batch(vert_colors, coords_3d)
                _col_cache["color_key"] = color_key
                _last_color_compute_time = now

    mvp = gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix()

    if _col_cache["batch_col"]:
        sh = gpu.shader.from_builtin('SMOOTH_COLOR')
        gl_enable(GL_POLYGON_OFFSET_FILL)
        gl_polygon_offset(-0.5, -0.5)
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)
        sh.bind()
        _col_cache["batch_col"].draw(sh)
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
        gl_polygon_offset(0.0, 0.0)
        gl_disable(GL_POLYGON_OFFSET_FILL)

    if _topo_cache["batch_wire"]:
        sh = get_custom_wire_shader()
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.line_width_set(1.0)
        sh.bind()
        sh.uniform_float("ModelViewProjectionMatrix", mvp)
        sh.uniform_float("color", _WIRE_COLOR)
        _topo_cache["batch_wire"].draw(sh)

    sh = get_custom_point_shader()
    gpu.state.program_point_size_set(True)
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    if _sel_cache["batch_unsel"]:
        gpu.state.point_size_set(4.5)
        sh.bind()
        sh.uniform_float("ModelViewProjectionMatrix", mvp)
        sh.uniform_float("color", _WIRE_COLOR)
        _sel_cache["batch_unsel"].draw(sh)
    if _sel_cache["batch_sel"]:
        gpu.state.point_size_set(20.0)
        sh.bind()
        sh.uniform_float("ModelViewProjectionMatrix", mvp)
        sh.uniform_float("color", (1.0, 0.85, 0.0, 1.0))
        _sel_cache["batch_sel"].draw(sh)
    gpu.state.program_point_size_set(False)
    gpu.state.point_size_set(1.0)


def _draw_hud():
    context = bpy.context
    if not context.space_data or context.space_data.type != 'VIEW_3D':
        return
    font_id = 0
    label = "MULTI COLOR MODE"
    fg_color = (1.0, 0.4, 0.7, 1.0)
    blf.size(font_id, 24)
    text_w, _ = blf.dimensions(font_id, label)
    region_width = context.region.width
    center_x = max(0, region_width // 2 - int(text_w) // 2)
    y_offset = 25
    blf.position(font_id, center_x + 2, y_offset + 2, 0)
    blf.color(font_id, 0.0, 0.0, 0.0, 0.85)
    blf.draw(font_id, label)
    blf.position(font_id, center_x, y_offset, 0)
    blf.color(font_id, *fg_color)
    blf.draw(font_id, label)


# ═══════════════════════════════════════════════════════════════════════════
#  Public lifecycle API
# ═══════════════════════════════════════════════════════════════════════════

def _disable_native_overlay():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                try:
                    area.spaces.active.overlay.show_vertex_group_weights = False
                except Exception:
                    pass


def _restore_native_overlay():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                try:
                    area.spaces.active.overlay.show_vertex_group_weights = True
                except Exception:
                    pass


def _start_handlers():
    global _active, _draw_handle, _hud_handle
    if _active:
        return
    _invalidate_all()
    global _bone_color_map, _last_mesh_name
    _bone_color_map = None
    _last_mesh_name = ""
    _disable_native_overlay()
    _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')
    _hud_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_hud, (), 'WINDOW', 'POST_PIXEL')
    _active = True


def _stop_handlers():
    global _active, _draw_handle, _hud_handle
    if not _active:
        return
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    if _hud_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_hud_handle, 'WINDOW')
        _hud_handle = None
    _restore_native_overlay()
    _active = False


def _active_obj_is_mask() -> bool:
    obj = bpy.context.active_object
    storage = getattr(obj, "superskin_storage", None) if obj is not None else None
    return bool(storage is not None and storage.active_is_mask)


def start():
    """User-facing enable. Suppressed (but remembered) while the active VG
    is the mask row — see _watcher_tick()."""
    global _user_enabled, _suppressed_by_mask
    _user_enabled = True
    if _active_obj_is_mask():
        _suppressed_by_mask = True
        return
    _suppressed_by_mask = False
    _start_handlers()


def stop():
    """User-facing disable. Clears the "want it on" intent entirely, so
    switching away from the mask row later does not auto-resume it."""
    global _user_enabled, _suppressed_by_mask
    _user_enabled = False
    _suppressed_by_mask = False
    _stop_handlers()


def toggle():
    stop() if _user_enabled else start()


def is_enabled() -> bool:
    """User-facing on/off state — True even while temporarily suppressed
    by the mask row, since the user's own intent is still "on"."""
    return _user_enabled


_WATCH_INTERVAL = 0.1


def _watcher_tick():
    """bpy.app.timers watcher, two independent jobs per tick:

    1. Auto-stop the GPU handlers while the active VG is the mask row,
       auto-resume when it changes back to a real bone — only when the
       user's own toggle currently wants this on. Nothing else can observe
       an obj.superskin_storage.active_is_mask change outside the draw
       cycle without depsgraph support (custom PropertyGroup toggles don't
       reliably trigger depsgraph_update_post — see docs/bug-history).

    2. Self-detect staleness and force a redraw. Weight-apply and undo both
       bump obj["__ssp_deform_gen"] (see docs/bug-history/0010), which is
       already part of topo_key/color_key — so the *next* draw would
       correctly notice and rebuild. The gap is that nothing guarantees a
       *next draw actually happens* promptly after those operations; the
       only previously-reliable trigger was nudging the timeline (which
       changes frame_current, another key field, and Blender redraws for
       playback regardless). Polling here — comparing a freshly-built key
       against what the cache last actually drew — makes multi_color_preview
       responsible for noticing its own staleness, instead of requiring
       every weight-mutating feature to remember to poke this one's redraw.
    """
    global _suppressed_by_mask
    if _user_enabled:
        is_mask = _active_obj_is_mask()
        if is_mask and _active:
            _suppressed_by_mask = True
            _stop_handlers()
            _tag_redraw_all()
        elif not is_mask and _suppressed_by_mask and not _active:
            _suppressed_by_mask = False
            _start_handlers()
            _tag_redraw_all()

    if _active:
        obj = bpy.context.active_object
        if obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT':
            try:
                bm = bmesh.from_edit_mesh(obj.data)
                frame = bpy.context.scene.frame_current
                stale = (
                    _make_topo_key(obj, bm, frame) != _topo_cache.get("topo_key")
                    or _make_color_key(obj, bm, frame) != _col_cache.get("color_key")
                )
                if stale:
                    _tag_redraw_all()
            except Exception:
                pass

    return _WATCH_INTERVAL


def _tag_redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def cleanup():
    """Remove all draw handles — called from domain unregister()."""
    global _user_enabled, _suppressed_by_mask
    _user_enabled = False
    _suppressed_by_mask = False
    _stop_handlers()


def register():
    global _watch_timer_registered
    if not _watch_timer_registered:
        bpy.app.timers.register(_watcher_tick, first_interval=_WATCH_INTERVAL, persistent=True)
        _watch_timer_registered = True


def unregister():
    global _watch_timer_registered
    if _watch_timer_registered and bpy.app.timers.is_registered(_watcher_tick):
        bpy.app.timers.unregister(_watcher_tick)
    _watch_timer_registered = False
    cleanup()


def _invalidate_all():
    for k in list(_topo_cache.keys()):
        _topo_cache[k] = None
    for k in list(_sel_cache.keys()):
        _sel_cache[k] = None
    for k in list(_col_cache.keys()):
        _col_cache[k] = None
