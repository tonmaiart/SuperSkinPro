# 0007 — Full GPU cache invalidation + Python-only undo checksum causing severe lag on bone hover, bone select, and layer switch

**Date:** 2026-06-19
**Area:** `core/shaders/shader_manager.py`, `core/ui_controller/layer_crud.py`, `core/ui_controller/ui_controller.py`, `core/ui_controller/undo_manager.py`

## Symptom

Noticeable stutter/lag in three separate interactions:
1. Dragging the mouse during the bone picker modal (`OBJECT_OT_mw_pick_bone`) — every hover-over-a-new-bone frame felt sluggish.
2. Clicking a row in the Deform Bones list to change the active bone.
3. Switching the active layer in the Layers tab.

None of these interactions touch mesh topology or do any heavy weight math — they only change which bone/layer is "active." The lag was disproportionate to the actual amount of data being changed.

## Root cause (two independent issues)

**1. `ShaderManager._deferred_invalidate()` always called full `invalidate_and_redraw()`.**

Any write to `obj.superskin_storage.last_clicked_index`, `obj.superskin_storage.selected_names`, or any `ss_*` mesh custom property fires Blender's `depsgraph_update_post`. `ShaderManager._on_depsgraph_update` schedules `_deferred_invalidate()` via a one-shot timer whenever `obj` or `obj.data` appears in `depsgraph.updates` — which is true for all three interactions above, every single frame during bone-picker hover.

`invalidate_and_redraw()` clears `topo_cache`, `sel_cache`, AND `col_cache` for both `BoneMode` and `MaskMode`. The next draw call then has to redo `extract_deformed_coords()` (a `foreach_get` over every vertex), rebuild the wireframe `LINES` batch, rebuild the selection `POINTS` batches, AND recompute vertex colors — even though only the active bone (a pure colour input) changed.

This was unnecessary: `BoneMode.make_color_key()` already includes `active_vg_id` in its cache key, and `visualizer_base.make_draw_callback`'s own per-frame key-diff check already detects an `active_vg_id` change and rebuilds the colour batch on its own. Likewise `topo_key` already includes vert/edge/face counts, so genuine topology changes are self-detected regardless of any external invalidation call. The full invalidate was pure duplicated, wasted work for selection-only changes.

**2. `undo_manager._deform_checksum()` is an unaccelerated Python O(vertices × groups) loop, called on every weight op and every layer switch.**

```python
def _deform_checksum(obj) -> int:
    if obj.mode == 'EDIT':
        obj.update_from_editmode()
    h = 0
    for v in obj.data.vertices:
        for g in v.groups:
            h = (h * 1000003 + hash((v.index, g.group, round(g.weight, 5)))) & 0xFFFFFFFF
    return h
```

`sync_checksum()` calls this after every weight operation (`pipeline.finish()`), after `switch_to_layer()`, and after `init_layer_system()`. For a mesh with thousands of vertices and multiple vertex groups, this pure-Python nested loop with per-entry `hash()`/`round()` calls is the single biggest cost on every layer switch — there is no Rust-accelerated path for it at all, unlike almost every other hot-path calculation in this codebase.

## Why it wasn't obvious

Both mechanisms are "correctness-first" catch-alls that someone reasonably added to be safe: the depsgraph handler exists to catch any change that doesn't show up cleanly in a cache key, and the checksum exists to gate undo restoration safely. Neither looks wrong in isolation — the bug is that they're **too conservative for how often they actually fire**. A pure selection change (hover, bone click, layer click) was being treated identically to "the user just painted weights on 5,000 vertices," even though the former needed at most a colour-only recompute and the latter's checksum is only meaningfully needed around actual weight-mutating undo boundaries, not every UI navigation click.

## Fix

1. **`core/shaders/shader_manager.py`** — `_deferred_invalidate()` now calls `ShaderManager.invalidate_color_only()` instead of `invalidate_and_redraw()`. Topology changes are still caught correctly because `topo_key`/`sel_key` comparisons run independently every frame regardless of what this handler does. `ShaderManager._on_undo()` was left untouched (still full invalidate) since undo/redo can jump across arbitrary topology states.

2. **`core/ui_controller/ui_controller.py` / `layer_crud.py`** — `switch_to_layer()` no longer calls the full-invalidate `refresh_visualizer()`. A new color-only refresh path was used instead, since switching the active layer changes weight/colour data only and never mesh topology.

3. **`core/ui_controller/undo_manager.py`** — `_deform_checksum()` was moved to a Rust-accelerated implementation (new `rust_logic/src/checksum.rs`, exposed as `rust_deform_checksum`), following the same `RustGateway`-with-vanilla-fallback pattern used by every other hot-path calculation in this codebase. The vanilla Python loop above is kept as the fallback.

## How it was diagnosed

Traced both lag reports back through the call chain without runtime profiling:
- Bone-hover lag → `mw_pick_bone.modal()` writes `last_clicked_index` every `MOUSEMOVE` → `depsgraph_update_post` → `ShaderManager._on_depsgraph_update` → `_deferred_invalidate` → confirmed it called the *full* invalidator, then checked `make_color_key` to confirm `active_vg_id` was already part of the cache key (meaning the full invalidate added cost without adding correctness).
- Layer-switch lag → `layer_crud.switch_to_layer()` → traced every call it makes → found both `ctrl.refresh_visualizer()` (full invalidate, same issue as above) and `undo_manager.sync_checksum()` → inspected `_deform_checksum()` and found an unaccelerated nested Python loop with no `RustGateway`, unlike every sibling calculation module in `core/weight_calculator/`.

## General lesson

When a cache-invalidation or safety-checksum mechanism is reused as a catch-all across many call sites, periodically audit how *often* each call site actually fires relative to how much data really changed. A "just invalidate everything to be safe" handler that's fine when triggered by an explicit weight-paint operation becomes a serious perf bug when the same handler also fires on every mouse-move during interactive picking. Likewise, any embarrassingly-parallel-style loop over `vertices × groups` in this codebase should default to a Rust-accelerated implementation from day one — `_deform_checksum` was the one exception that had slipped through without one.
