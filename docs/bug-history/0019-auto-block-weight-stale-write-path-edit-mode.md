> [RESOLVED 2026-06-27] `auto_block_domain.py` now reads via `ctrl._read_active_layer_int()`
> and writes via `ctrl._write_active_layer_string()`, routing both through the BMesh
> temp VG bridge in Edit Mode. See `docs/core-interfaces/edit_mode_weight_write_pattern.md`
> for the canonical pattern.

# 0019 — Auto Block Weight stale write path bypasses temp VG bridge in Edit Mode

**Date:** 2026-06-27
**Area:** `features/auto_block_weight/auto_block_domain.py`

## Symptom

After running Auto Block Weight in Edit Mode (Skin Mode), the layer list UI
showed bone influence symbols for the assigned vertices, but the viewport
shader heatmap and armature-deformed mesh coordinates did not update. Exiting
and re-entering Skin Mode caused the symbols to disappear entirely, confirming
the weight data was never persisted to the active store.

## Root cause

`auto_block_domain.py` used `core_facade.get_active_layer_dict()` to read
and `core_facade.write_layer_dict()` to write. Both facade wrappers delegate
directly to `ctrl.storage.read_active_layer_dict()` / `ctrl.storage.write_layer_dict()`,
which read and write `ss_layer_N` ID properties — the Object Mode store.

After the `0016` undo redesign, `ss_layer_N` for the active layer is not the
source of truth during Edit Mode. The real store is the `__ssp_*` BMesh temp
VGs, which are tracked by Blender's BMesh undo system. `pipeline.flatten_to_mesh_edit()`
reads from those temp VGs, so writing to `ss_layer_N` had no effect on
deformation or on the next flatten call.

The UI list showed symbols because the layer list widget reads from the
in-memory storage dict (updated by the facade write), while the viewport
shader and mesh deformation both ultimately depend on the temp VGs and the
evaluated mesh — two separate data chains that can diverge silently.

## Why it wasn't obvious

`core_facade.write_layer_dict()` is a public CoreFacade method documented as
"Commits a nested weight dictionary back to the active layer slot." Nothing
in the doc surface (or the method name) indicates it does not route through
the temp VG bridge. The UI list updating correctly after the op created the
false impression that the write had succeeded; only the viewport's failure
to update revealed the discrepancy. The reset on exit/re-enter Skin Mode was
the definitive indicator: Exit Edit Mode bakes from temp VGs back to
`ss_layer_N`, so any `ss_layer_N` write that happened during Edit Mode is
overwritten at that point, erasing the assigned weights.

This bug had the same structure as `0018`, which fixed the same issue in
`weight_apply_domain`. The `0018` fix updated the core read/write paths and
the `weight_apply_domain`, but did not audit other domains that also used
storage-layer read/write calls directly.

## Fix

**`features/auto_block_weight/auto_block_domain.py`**

Replaced the facade read/write pair with the UIController escape-hatch
pattern established by `weight_apply_domain`:

1. `bone_to_id, id_to_bone = ctrl.storage.get_unified_mapping(ctrl.obj)` —
   obtain the unified name↔ID mapping (includes synthetic orphan IDs).
2. `ctrl._read_active_layer_int(bone_to_id)` — reads from BMesh temp VGs in
   Edit Mode (or `ss_layer_N` outside Edit Mode); also populates
   `ctrl._orphan_entries` for bones unknown to the mapping.
3. Convert int dict → string dict in-line for the assignment and normalization
   logic (which operates on bone names).
4. Convert result string dict → int dict in-line.
5. `ctrl._write_active_layer_string(result_int, id_to_bone, {}, is_mask_mode=False)` —
   writes to BMesh temp VGs in Edit Mode, re-merges orphan entries, prunes
   zero-weight bones.
6. `core_facade.finish(color_only=True)` — flattens temp VGs to bone VGs,
   bumps deform generation, and schedules a visualizer redraw.

## How it was diagnosed

Compared `auto_block_domain.py` side by side with the working
`weight_apply_domain.py`. The working domain uses `ctrl._read_active_layer_int()`
and `ctrl._write_active_layer_string()` for its read/write cycle. The broken
domain used `core_facade.get_active_layer_dict()` and
`core_facade.write_layer_dict()`, which trace to `ctrl.storage.*` — the
storage-service layer that is unaware of the temp VG bridge. Reading
`core/facade.py` confirmed that neither facade wrapper calls through to
`_read_active_layer_int` or `_write_active_layer_string`.

## General lesson

`core_facade.get_active_layer_dict()` and `core_facade.write_layer_dict()`
are **not safe for Edit Mode weight operations**. They bypass the temp VG
bridge and silently read/write the wrong store. Any feature domain that
modifies active-layer weights in Edit Mode **must** use the UIController
escape-hatch pattern documented in
`docs/core-interfaces/edit_mode_weight_write_pattern.md`. When a new domain
is added that writes weights, check this pattern first before reaching for
the facade write methods.
