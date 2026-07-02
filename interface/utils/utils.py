"""UI Utility Garbage Collector & Shared Logic for SuperSkinPro.

Consolidated from:
  - utils.py (force_open/force_close)
  - ui_influence_list.py (wildcard, depth caches, display order, influence scanner, visual order)
  - ui_layer_list.py (layer target resolver, visualizer enforcer, sync_layers_to_ui_collection)
  - panel_main.py (_auto_init_layers, _auto_init_pending)
  - widget_layers.py (depsgraph / load handlers)
"""

import bpy
import json
import traceback

from ...core.facade import CoreFacade
from ...core_subsystems.topology_cache_manager import TopologyCacheManager
from ...core.layer_storage.storage_service import LayerStorageService
from ...core_subsystems.rust_weight_engine import RustWeightEngine
from ...core.bone_identity import BoneIdentityService
from ...core_subsystems.debug_logging import DebugLogService
# LayerCompositor kept function-scoped in sync_bones_to_ui_collection —
# hoisting it triggers a circular import through core_subsystems → features → ui.utils.


# ═══════════════════════════════════════════════════════════════════════════
#  Guard helpers — shared validity checks reused across operators/ops_*.py
# ═══════════════════════════════════════════════════════════════════════════


def _is_valid_mesh(obj):
    """True if *obj* is a usable mesh object."""
    return bool(obj) and obj.type == 'MESH'


def _has_layer_system(obj):
    """True if *obj* is a valid mesh with an initialised layer system."""
    return _is_valid_mesh(obj) and "ss_layers_meta" in obj.data


# ═══════════════════════════════════════════════════════════════════════════
#  Tab / panel helpers (from original utils.py)
# ═══════════════════════════════════════════════════════════════════════════


def exit_mask_mode_if_active(context, obj):
    """If mask mode is active (superskin_is_mask_mode flag), exit it.

    Saves the current mode, switches to OBJECT if needed,
    exits the mask editing context, clears flags,
    restores the visualizer, and returns to the previous mode.

    Only triggers when ``superskin_is_mask_mode`` is explicitly True.

    Suppresses the auto-close-panel-on-mode-exit side effect for the
    duration of the round-trip so callers that are *not* already wrapped
    by ``_run_in_object_context`` (e.g. ``BoneListAdapter.on_single_select``) don't trigger a spurious panel close.

    Returns True if mask mode was active and exited, False otherwise.
    """
    in_mask = context.scene.superskin_is_mask_mode
    if not in_mask:
        return False

    ctrl = CoreFacade(context).get_ctrl()
    prev_mode = obj.mode if obj else 'OBJECT'
    was_suppressing = context.scene.superskin_internal_transaction
    context.scene.superskin_internal_transaction = True
    try:
        if prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        context.scene.superskin_is_mask_mode = False
        active_vg_idx = obj.vertex_groups.active_index
        if active_vg_idx >= 0:
            ctrl.exit_mask_editing_context(active_vg_idx)
        ctrl.restore_visualizer_from_mask()
        if prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=prev_mode)
    finally:
        context.scene.superskin_internal_transaction = was_suppressing
    return True


def force_open_super_skin_tab():
    """Open the 3D View sidebar and switch to the SuperSkinPro panel."""
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if not area:
        return

    # Force the sidebar (N-panel) open if it's collapsed
    if not area.spaces.active.show_region_ui:
        area.spaces.active.show_region_ui = True

    # Switch the N-panel category to SuperSkinPro
    ui_region = next((r for r in area.regions if r.type == 'UI'), None)
    if ui_region:
        with bpy.context.temp_override(area=area, region=ui_region):
            ui_region.active_panel_category = "Super Skin Pro"
            ui_region.tag_redraw()


def force_close_tab():
    """Collapse the 3D View sidebar only if 'Super Skin Pro' is the active panel category."""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            ui_region = next((r for r in area.regions if r.type == 'UI'), None)
            if ui_region and ui_region.active_panel_category == "Super Skin Pro":
                with bpy.context.temp_override(area=area):
                    area.spaces.active.show_region_ui = False


def _run_in_object_context(context, callback, *args):
    """Execute *callback(*args)* in OBJECT mode, restoring the previous mode.

    Many layer-management operations require the mesh to be in OBJECT mode.
    This helper encapsulates the save → switch → execute → restore pattern
    so that operators can stay concise.

    Suppresses the auto-close-panel-on-mode-exit side effect for the
    duration of the round-trip.  Returns whatever *callback* returns.
    """
    obj = context.active_object
    prev_mode = obj.mode
    was_suppressing = context.scene.superskin_internal_transaction
    context.scene.superskin_internal_transaction = True
    try:
        if prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        result = callback(*args)
        if prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=prev_mode)
        return result
    finally:
        context.scene.superskin_internal_transaction = was_suppressing


# ═══════════════════════════════════════════════════════════════════════════
#  Auto-init layer system (from panel_main.py)
# ═══════════════════════════════════════════════════════════════════════════

_auto_init_pending = False


def _auto_init_layers():
    """One-shot timer: initialise the layer system on the active mesh.

    Must run outside the draw() callback because Blender forbids writing
    to ID data-blocks (Mesh custom properties) during panel drawing.

    Returns None on every path so Blender unregisters the timer.
    """
    global _auto_init_pending
    ctx = bpy.context
    obj = ctx.active_object

    if not (obj and obj.type == "MESH" and "ss_layers_meta" not in obj.data):
        _auto_init_pending = False
        return None  # Explicit unregistration: conditions not met

    try:
        ctrl = CoreFacade(ctx).get_ctrl()
        ctrl.init_layer_system()

        for window in ctx.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    finally:
        _auto_init_pending = False

    return None  # Explicit unregistration: success path


# ═══════════════════════════════════════════════════════════════════════════
#  Performance caches (from ui_influence_list.py)
# ═══════════════════════════════════════════════════════════════════════════

# ⚡ Performance cache: bone display order — invalidated when armature/mesh changes
_display_order_cache = {}
_display_order_cache_key = None  # (mesh_name, arm_name)

# ⚡ Performance cache: influence scanner visible bones — invalidated on layer/blob change
_influence_visible_cache = {}
_influence_visible_cache_key = None  # (id(mesh_data), active_layer_idx, blob_hash)


def _get_cached_display_order(arm_obj, deform_bones):
    """⚡ Retain cache mechanism exclusively for bone item sequencing order.

    Hoisted import: TopologyCacheManager (was function-scoped at line 183).
    """
    global _display_order_cache, _display_order_cache_key

    mesh_name = ""
    arm_name = ""
    if arm_obj:
        arm_name = arm_obj.name
        if arm_obj.data:
            mesh_name = getattr(arm_obj.data, 'name', '')

    cache_key = (mesh_name, arm_name, len(deform_bones))

    if _display_order_cache_key == cache_key and _display_order_cache:
        return _display_order_cache

    try:
        _display_order_cache = TopologyCacheManager.compute_bone_display_order(arm_obj, deform_bones)
    except Exception as e:
        print(f"[SuperSkinPro Error] Failed computing display_order: {e}")
        _display_order_cache = list(deform_bones)

    _display_order_cache_key = cache_key
    return _display_order_cache


def _get_visible_influence_bones(context, data):
    """⚡ Pure deterministic weight scanner cache. Stable during selection changes.

    In Edit Mode with temp VGs loaded, the active layer's live weights sit
    in the __ssp_* BMesh channels and haven't been baked back to ss_layer_N
    yet (see docs on the 0016 undo redesign) — reading ss_layer_N here would
    silently show stale/empty data while painting. Mirrors the same
    mode-aware routing as core/facade/read.py's _read_active_layer_int().

    The ss_layer_N blob hash used to key the cache in Object Mode doesn't
    move at all during an Edit-Mode paint stroke (nothing is baked back
    until layer switch/mode exit), so it can't be reused as-is here. Instead
    this branch keys on ShaderManager.get_deform_generation() — the same
    process-wide counter core/facade/write.py's finish() and
    write_active_layer_from_calc() already bump on every completed weight
    write, and only on that (not on mouse-move/redraw) — so draw() calls
    between strokes still hit the cache instead of re-running the Rust
    scanner on every redraw tick.

    Hoisted imports: LayerStorageService, RustWeightEngine (were function-scoped,
    absolute 'SuperSkinPro' references at lines 221-222).
    """
    global _influence_visible_cache, _influence_visible_cache_key

    from ...core.layer_storage.temp_vg_bridge import has_temp_vgs, read_temp_vgs_from_bm
    from ...core.shaders.shader_manager import ShaderManager

    mesh_data = data.data
    in_edit_temp = data.mode == 'EDIT' and has_temp_vgs(data)

    if in_edit_temp:
        cache_key = (id(mesh_data), 'EDIT_TEMP', ShaderManager.get_deform_generation())
    else:
        active_layer_idx = mesh_data.get("ss_active_layer", 0)
        raw_blob = mesh_data.get(f"ss_layer_{active_layer_idx}", "")
        cache_key = (id(mesh_data), active_layer_idx, hash(raw_blob))

    if _influence_visible_cache_key == cache_key:
        return set(_influence_visible_cache)

    storage = LayerStorageService(mesh_data)

    if in_edit_temp:
        import bmesh as _bm_mod
        bm = _bm_mod.from_edit_mesh(mesh_data)
        raw_layer_dict, _, _ = read_temp_vgs_from_bm(bm, data)
    else:
        raw_layer_dict = storage.read_active_layer_dict()

    bone_to_id, id_to_bone = storage.get_local_mapping(data)

    layer_int: dict[int, dict[int, float]] = {}
    for v_idx, weights in raw_layer_dict.items():
        v_int = int(v_idx)
        inner = {}
        if isinstance(weights, dict):
            for b_name, w in weights.items():
                b_id = bone_to_id.get(b_name)
                if b_id is not None:
                    inner[b_id] = float(w)
        layer_int[v_int] = inner

    rust = RustWeightEngine("influence_scanner")
    rust_set = rust.call("rust_get_visible_influence_bones", layer_int)

    visible_bones = set()
    if rust_set:
        for b_id in rust_set:
            b_name = id_to_bone.get(b_id)
            if b_name:
                visible_bones.add(b_name)

    DebugLogService.log(
        "core_pipeline",
        f"_get_visible_influence_bones() recompute: obj={data.name!r} "
        f"in_edit_temp={in_edit_temp} raw_layer_dict verts={len(raw_layer_dict)} "
        f"rust_set={rust_set!r} visible_bones={sorted(visible_bones)!r} "
        f"obj.mode={getattr(data, 'mode', '?')}",
    )

    _influence_visible_cache = frozenset(visible_bones)
    _influence_visible_cache_key = cache_key
    return set(visible_bones)


def _get_display_order_impl(context, data):
    """Hierarchy‑ordered ``vertex_groups`` indices (deform bones only; a
    vertex group whose name isn't a current deform bone is dropped from
    the order entirely — this is the Deform Bones list, not a generic
    vertex-group list). Used only by ``sync_bones_to_ui_collection`` now
    (moved out of ``widget_deform_bones.py`` during the bones-list mirror-
    collection refactor to avoid a circular import — that module imports
    from this one already, and the sync function below needs this same
    ordering at write time instead of draw time).

    Hoisted import: traceback (was function-scoped at line 263).
    """
    items = data.vertex_groups
    arm_obj = next((m.object for m in data.modifiers
                    if m.type == 'ARMATURE' and m.object), None)
    deform_bones = set()
    if arm_obj:
        deform_bones = {b.name for b in arm_obj.data.bones if b.use_deform}

    if arm_obj and deform_bones:
        try:
            ordered_names = _get_cached_display_order(arm_obj, deform_bones)
        except Exception:
            traceback.print_exc()
            return list(range(len(items)))

        name_to_idx = {item.name: i for i, item in enumerate(items)}
        result = []
        for name in ordered_names:
            idx = name_to_idx.get(name)
            if idx is not None:
                result.append(idx)
        return result
    else:
        return list(range(len(items)))


def sync_bones_to_ui_collection(obj):
    """Mirror the Deform Bones list's paintable rows (real vertex groups,
    hierarchy-ordered) plus orphaned-weight pseudo-rows (see
    ``core.bone_identity``) into ``obj.superskin_bones_collection`` — the
    real ``bpy_prop_collection`` the unified ``template_list`` widget binds
    to. Mirrors ``sync_layers_to_ui_collection`` above for the same reason:
    Blender's ``template_list`` can only iterate a real RNA collection, and
    orphan rows by definition have no backing ``VertexGroup``.

    Write-only context (depsgraph handler / operator) — never call from
    draw(), same constraint as ``BoneIdentityService.backfill_and_scan()``.
    Mirrors *every* paintable/orphan row unfiltered; ``bone_list_filter_mode``
    stays a draw-time concern handled by the UIList's ``filter_items``,
    exactly as it did against the real ``vertex_groups`` collection before
    this refactor — baking it in here would mean switching the filter mode
    wouldn't visibly update the list until the next depsgraph tick.

    Hoisted imports: BoneIdentityService, LayerStorageService, LayerCompositor
    (were function-scoped, absolute 'SuperSkinPro' references at lines 309, 329-330).
    """
    if not obj or obj.type != 'MESH':
        return

    DebugLogService.log("bone_id", f"sync_bones_to_ui_collection() ENTRY: obj={obj.name!r}")

    order = _get_display_order_impl(None, obj)
    vg_list = obj.vertex_groups
    orphans = BoneIdentityService.get_scan_for_object(obj)

    # Re-derive the native template_list highlight from the real "active
    # bone" source of truth on every rebuild (last_clicked_index /
    # active_orphan_name) — col.clear()+add() below reassigns every row's
    # position, so superskin_bones_idx must be recomputed each time too, or
    # it silently points at whatever bone now happens to sit at the old
    # integer position. Mirrors how sync_layers_to_ui_collection re-derives
    # superskin_layers_idx from ss_active_layer on every rebuild.
    storage = obj.superskin_storage
    active_orphan = storage.active_orphan_name
    active_vg_name = None
    if (not active_orphan and not storage.active_is_mask
            and 0 <= storage.last_clicked_index < len(vg_list)):
        active_vg_name = vg_list[storage.last_clicked_index].name

    try:
        from ...core_subsystems.layer_compositor import LayerCompositor
        _sto = LayerStorageService(obj.data)
        _meta = _sto.read_meta_list()
        locks = LayerCompositor.get_bone_locks(_meta, _sto.get_active_layer_index())
    except Exception:
        locks = {}

    col = obj.superskin_bones_collection
    col.clear()

    mask_item = col.add()
    mask_item.name = "Mask"
    mask_item.vg_index = -1
    mask_item.is_orphan = False
    mask_item.is_mask = True
    if storage.active_is_mask:
        obj.superskin_bones_idx = len(col) - 1

    DebugLogService.log(
        "bone_id",
        f"sync_bones_to_ui_collection(): mask row added at col index 0, "
        f"is_mask={mask_item.is_mask} active_is_mask={storage.active_is_mask}",
    )

    for vg_idx in order:
        if vg_idx < 0 or vg_idx >= len(vg_list):
            continue
        vg = vg_list[vg_idx]
        item = col.add()
        item.name = vg.name
        item.vg_index = vg_idx
        item.is_orphan = False
        item.lock_weight = locks.get(vg.name, False)
        if active_vg_name and vg.name == active_vg_name:
            obj.superskin_bones_idx = len(col) - 1

    for orphan in orphans:
        item = col.add()
        item.name = orphan["name"]
        item.vg_index = -1
        item.is_orphan = True
        item.lock_weight = locks.get(orphan["name"], False)
        item.classification = orphan.get("classification", "")
        item.suggested_target = orphan.get("suggested_target") or ""
        if active_orphan and orphan["name"] == active_orphan:
            obj.superskin_bones_idx = len(col) - 1

    DebugLogService.log(
        "bone_id",
        f"sync_bones_to_ui_collection() EXIT: {len(col)} total rows "
        f"({len(order)} bone, {len(orphans)} orphan, 1 mask), "
        f"superskin_bones_idx={obj.superskin_bones_idx}",
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Layer helpers (from ui_layer_list.py)
# ═══════════════════════════════════════════════════════════════════════════


def _resolve_layer_target(obj, layer_index_prop):
    """Return the slot index of the layer the user is operating on.

    Prefers the explicit *layer_index_prop* when set (≥0); otherwise
    reads the currently highlighted item from the UI collection.

    Args:
        obj: The active mesh object.
        layer_index_prop: Value of the operator's ``layer_index`` property.

    Returns:
        ``int`` — the layer slot index, or ``-1`` if unresolvable.
    """
    if layer_index_prop >= 0:
        return layer_index_prop
    col = obj.superskin_layers_collection
    idx = obj.superskin_layers_idx
    if 0 <= idx < len(col):
        return col[idx].index
    return -1


def _select_only_layer(obj, slot_index: int):
    """Force the layer multi-select pool to contain only *slot_index*.

    Layer CRUD operators (add/remove/move/duplicate) change which layer is
    active without going through LayerListAdapter.write_selection() — the
    only other place that writes layer_selected_indices /
    layer_selection_history. Without this, a previously-selected layer
    lingers in layer_selected_indices after the active layer changes, so
    SuperSkinListMixin.draw_item() renders it with selected=True,
    active=False (the alert/highlight style) even though only the new
    active layer should appear selected.

    Call this right after the active layer changes as a result of a CRUD
    operation, passing the resulting active slot index.
    """
    storage = obj.superskin_storage
    storage.layer_selected_indices = f",{slot_index},"
    storage.layer_selection_history = str(slot_index)


def _enforce_visualizer_from_tab_state(context):
    """Re-apply the correct viewport shader after a layer mutation.

    Reads ``superskin_is_mask_mode`` directly:
      Mask row active → force MASK visualizer
      otherwise        → restore the mode that was active before MASK (SINGLE/MULTI)
    """
    try:
        ctrl = CoreFacade(context).get_ctrl()
        is_mask = getattr(context.scene, "superskin_is_mask_mode", False)
        if is_mask:
            ctrl.set_visualizer_mode('MASK')
        else:
            ctrl.restore_visualizer_from_mask()
    except Exception:
        pass
    # Redraw all VIEW_3D areas so the shader change is visible instantly
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


_last_known_meta = {}


def sync_layers_to_ui_collection(obj):
    meta_raw = obj.data.get("ss_layers_meta")
    if not meta_raw:
        return
    try:
        meta = json.loads(meta_raw)
    except Exception as e:
        print(f"Layer system synchronisation failed: {e}")
        return

    col = obj.superskin_layers_collection
    active_idx = obj.data.get("ss_active_layer", 0)

    col.clear()
    for display_pos, entry in enumerate(meta):
        slot_idx = entry.get("index", display_pos)
        item = col.add()
        item.name = entry.get("name", f"Layer {display_pos}")
        item.index = slot_idx
        item.visible = entry.get("visible", True)
        if slot_idx == active_idx:
            obj.superskin_layers_idx = display_pos

    global _last_known_meta
    _last_known_meta[obj.data.name] = meta_raw


# ═══════════════════════════════════════════════════════════════════════════
#  Depsgraph / Load handlers (relocated from widget_layers.py)
# ═══════════════════════════════════════════════════════════════════════════

@bpy.app.handlers.persistent
def _superskin_layers_depsgraph_handler(scene, depsgraph):
    for update in depsgraph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object) and obj.type == 'MESH':
            try:
                if "ss_layers_meta" in obj.data:
                    sync_layers_to_ui_collection(obj)
                    # Same gate as the layers sync above — the Deform
                    # Bones mirror collection only matters for meshes
                    # SuperSkinPro has already initialized a layer system
                    # on, and reuses this handler rather than adding a
                    # second depsgraph subscriber for the same update loop.
                    sync_bones_to_ui_collection(obj)
            except Exception as e:
                DebugLogService.log(
                    "bone_id",
                    f"_superskin_layers_depsgraph_handler() EXCEPTION on "
                    f"obj={getattr(obj, 'name', '?')!r}: {e!r}\n{traceback.format_exc()}",
                )


@bpy.app.handlers.persistent
def _superskin_layers_load_handler(dummy):
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and "ss_layers_meta" in obj.data:
            try:
                sync_layers_to_ui_collection(obj)
                sync_bones_to_ui_collection(obj)
            except Exception as e:
                DebugLogService.log(
                    "bone_id",
                    f"_superskin_layers_load_handler() EXCEPTION on "
                    f"obj={obj.name!r}: {e!r}\n{traceback.format_exc()}",
                )

# ═══════════════════════════════════════════════════════════════════════════
#  Registration
# ═══════════════════════════════════════════════════════════════════════════


def register():
    bpy.app.handlers.depsgraph_update_post.append(_superskin_layers_depsgraph_handler)
    bpy.app.handlers.load_post.append(_superskin_layers_load_handler)


def unregister():
    try:
        bpy.app.handlers.load_post.remove(_superskin_layers_load_handler)
    except Exception:
        pass
    try:
        bpy.app.handlers.depsgraph_update_post.remove(_superskin_layers_depsgraph_handler)
    except Exception:
        pass