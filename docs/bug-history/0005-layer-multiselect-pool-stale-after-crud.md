# 0005 — Stale layer multi-selection after Add / Remove / Move / Duplicate

**Date:** 2026-06-18
**Area:** `ui/utils.py`, `operators/ops_interface.py`

## Symptom

After clicking a layer row in the Layers list (which highlights it as selected)
and then performing any CRUD operation — Add Layer, Remove Layer, Move Up/Down,
or Duplicate — the previously-clicked layer would render with the
alert/highlighted "selected but not active" style, *alongside* the new active
layer's normal highlight. The effect looked like a stray multi-selection that
the user never requested. Ctrl+Z would correctly revert the layer operation but
the visual ghosting persisted until the user clicked another layer row.

## Root cause

The layer-list row renderer (`SuperSkinListMixin.draw_item()`) decides how to
highlight a row by checking two independent state fields:

1. **`is_active()`** — reads `obj.superskin_layers_idx` (which points to the
   currently active layer in the UI collection). This is kept correct by
   `sync_layers_to_ui_collection()`, called at the end of every CRUD operator.

2. **`is_selected()`** — reads
   `obj.superskin_storage.layer_selected_indices`, a comma-bounded string of
   slot indices (e.g. `",2,4,"`). This is the multi-select pool, normally
   maintained by `LayerListAdapter.write_selection()` in `ui/widget_tools.py`,
   which fires from the generic `superskin.list_select_row` operator on every
   row click (including modifier clicks like Shift+click).

When `is_selected()==True` and `is_active()==False`, the row gets the alert
(highlighted) style — exactly what happens when a stale entry lingers in
`layer_selected_indices` after the active layer changes.

The four layer CRUD operators (`SUPERSKIN_OT_layer_add`,
`SUPERSKIN_OT_layer_remove`, `SUPERSKIN_OT_layer_move`,
`SUPERSKIN_OT_layer_duplicate`) call `UIController` methods directly via
`_run_in_object_context()` and never go through `LayerListAdapter.write_selection()`.
They update the active layer (which `sync_layers_to_ui_collection` reflects
correctly) but leave `layer_selected_indices` untouched. Result: whichever
layer was selected before the CRUD operation stays in the pool, and `draw_item()`
renders it with `selected=True, active=False` — the alert style — making it
look like a stray multi-selection.

## Why it wasn't obvious / why a first attempt didn't catch it

- The bug looks like a rendering glitch, not a state management bug. The
  highlighted row doesn't behave like a real selection (clicking it behaves
  normally; the CRUD operations work correctly on the active layer). A
  developer unfamiliar with the split between `is_active` and `is_selected`
  fields in the draw path would naturally look at the shader or the
  `draw_item()` logic first, not at a stale string property on a PropertyGroup.

- The two state fields live in entirely different storage locations
  (`superskin_layers_idx` on the object vs. `layer_selected_indices` on
  `obj.superskin_storage`) and are maintained by entirely different code
  paths (the depsgraph-driven `sync_layers_to_ui_collection` vs. the
  click-driven `LayerListAdapter.write_selection`). There's no single place
  in the codebase that explicitly acknowledges both fields need to stay in
  sync — the invariant is implicit and only observable through the
  `draw_item()` rendering outcome.

- The CRUD operators worked perfectly in every other respect — the correct
  layer became active, the viewport visualizer updated, undo worked — so
  nothing triggered an error or warning. The bug was purely cosmetic, which
  is the easiest class of bug to overlook during development.

## Fix

1. **`ui/utils.py`** — Added `_select_only_layer(obj, slot_index)` near the
   existing `_resolve_layer_target` helper. It sets
   `layer_selected_indices` to `",{slot_index},"` and
   `layer_selection_history` to `str(slot_index)`, matching exactly the format
   that `LayerListAdapter.write_selection()` would produce for a single-selection
   scenario.

2. **`operators/ops_interface.py`** — Each CRUD operator now calls
   `_select_only_layer` after the active layer changes:

   - **Add**: captures `create_layer`'s return value (`new_idx`) and calls
     `_select_only_layer(obj, new_idx)`.
   - **Remove**: reads `ctrl.active_layer_index` after `remove_layer`
     completes (the removal's internal fallback `switch_to_layer` updates it)
     and syncs to it.
   - **Move**: only syncs if `move_layer` returns `True` (the move actually
     happened), passing the original `target` index since `move_layer` changes
     display order but not which layer is active.
   - **Duplicate**: captures `duplicate_layer`'s return value (`new_idx`, or
     `-1` on failure) and syncs to it when valid. Also consolidated the two
     separate `UIController(context)` instantiations in the original code into
     a single `ctrl` variable (cleanup, same behavior).

   `SUPERSKIN_OT_layer_rename_active` and
   `SUPERSKIN_OT_layer_toggle_visible_by_item` were left untouched — neither
   changes which layer is active, so the existing selection pool is still
   valid after they run.

3. **Undo scope**: No `undo_manager.push()` calls were added.
   `layer_selected_indices` / `layer_selection_history` live on
   `obj.superskin_storage` (a PropertyGroup), not as `ss_*` mesh custom
   properties, so they are outside `LayerUndoManager`'s scope by design —
   consistent with how the bone-list selection fields are already handled.

## How it was diagnosed

The diagnostic traced the complete data flow from a layer row-click through
to the draw call:

1. **Identified the two independent state fields**: Grep for
   `layer_selected_indices` and `superskin_layers_idx` revealed they are
   written by completely disjoint code paths — the former only by
   `LayerListAdapter.write_selection()` in `ui/widget_tools.py`, the latter
   by `sync_layers_to_ui_collection()` in `ui/utils.py`.

2. **Confirmed the CRUD operators never touch the selection pool**: Grep for
   `layer_selected_indices` in `operators/ops_interface.py` returned no matches
   — confirming the operators never update the field.

3. **Confirmed the rendering path uses both fields independently**:
   `SuperSkinListMixin.draw_item()` calls `is_selected()` (reads
   `layer_selected_indices`) and `is_active()` (reads
   `superskin_layers_idx`), and applies the alert style when
   `selected=True and active=False`.

4. **Verified the format**: `read_selection()` and `is_selected()` in
   `LayerListAdapter` confirmed the comma-bounded string format
   (`",{idx},"`), so the fix writes in the exact same format.

## General lesson

When a widget's visual state is derived from two independently-maintained
state fields, any operation that mutates one field must also update the
other if the invariant between them has changed. The invariant here is:
after a CRUD operation changes which layer is active, the selection pool
should reflect exactly the new active layer (not the previous selection).
Without an explicit sync point, the two fields drift apart silently, and
the only observable symptom is a rendering artifact — the hardest kind of
bug to notice in a test pass but the most immediately visible to a user.
