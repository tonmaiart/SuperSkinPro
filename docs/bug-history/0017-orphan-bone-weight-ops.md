# 0017 — Orphan bones now fully supported in weight ops

**Date:** 2026-06-26
**Area:** `core/orphan_resolver/`, `core/ui_controller/ui_controller.py`,
          `core/ui_controller/operations.py`, `core/layer_storage/geometry.py`,
          `core/layer_storage/temp_vg_bridge.py`

## Symptom

Selecting an orphan bone row (ERROR icon) in the Deform Bones list and pressing
Add/Scale/Sharpen raised:

```
ValueError: No active Vertex Group selected
```

`_active_vg_id()` returned `None` because `last_clicked_index` was set to `-1`
(orphan bones have no real vertex group), so the guard clause rejected the op.

## Root Cause

Three separate gaps combined:

1. **`_active_vg_id()`** only checked `last_clicked_index` — had no code path
   for `active_orphan_name`.

2. **`_local_mapping()`** (used by all weight ops) only covers real vertex groups,
   so orphan bone weights were silently stashed in `_orphan_entries` and never
   passed to Rust. Rust never saw the orphan bone, so it couldn't modify it.

3. **`SUPERSKIN_OT_select_orphan_bone_row`** lived in `ui/widget_deform_bones.py`
   (a UI module), making it invisible to the core subsystem and registering after
   core weight ops — conceptually misplaced.

## Fix

### `core/orphan_resolver/` — new package

Moved `SUPERSKIN_OT_select_orphan_bone_row` here from `ui/widget_deform_bones.py`.
Registered in `core/__init__.py` between `bone_identity` and `license`.
`bl_idname = "superskin.select_orphan_bone_row"` is unchanged — no other files need
updating. Removed the orphan operator class and its registration from `widget_deform_bones.py`.
Renamed `_sync_bones_idx_to_mirror()` → `_sync_bones_idx_to_real_bone()` (orphan
sync path moved into the new ops.py as `_sync_bones_idx_to_orphan()`).

### `_active_vg_id()` — orphan path added

Now checks `active_orphan_name` first. If set, looks up the bone's synthetic int ID
via `get_unified_mapping()` and returns it. Rust treats synthetic ID 5 the same as
any real VG index 5 — it's just a number in the dict key.

### `_active_bone_name()` — new helper

Returns the active bone name regardless of real/orphan. Reads `active_orphan_name`
first, falls back to `vertex_groups[last_clicked_index].name`. No callers yet;
exposed for future use (clipboard, display, etc.).

### Weight ops use `get_unified_mapping()` instead of `_local_mapping()`

`add()`, `scale()`, `smooth()`, `sharpen()` now call
`ctrl.storage.get_unified_mapping(ctrl.obj)` which assigns stable synthetic int IDs
to orphan bones. The orphan bone's weight is now in `layer_int` (not stashed in
`_orphan_entries`), so Rust normalizes it correctly alongside real bones.

### `_write_active_layer_string()` — filtered `known_bone_names`

`_normalize_orphan_budget()` now receives only real-bone names
(`idx < len(obj.vertex_groups)`). Orphan bones with synthetic IDs are excluded so
any stashed unknown-bone weights still get budget-constrained correctly. When orphan
weights went through Rust, the budget check is a no-op (Rust already normalized ≤ 1.0).

### `_locks_by_id()` — unified mapping

Uses `get_unified_mapping()` so orphan bones that have explicit lock entries in
layer metadata are respected.

### `temp_vg_bridge.read_temp_vgs_to_layer()` — auto-prune on restore

Added `_prune_zero_weights()` call before returning. Orphan bone weights scaled to
zero by a weight op are purged from the layer dict at undo-restore time, not just at
write time.

## User Workflow (after fix)

1. Select orphan row (ERROR icon) → `active_orphan_name = "BoneThatWasDeleted"`.
2. Press Add → weight increases. Press Scale → weight scales. Press Smooth → smooths.
3. Scale to 0 on all selected verts → `_prune_zero_bones()` removes entry from storage.
4. `_purge_zeroed_orphans_from_all_layers()` removes it from all other layers + meta.
5. Next sync of `superskin_bones_collection` drops the orphan row from the list.

## Test Checklist

1. Select orphan row → `active_orphan_name` set, `last_clicked_index = -1` ✓
2. Shader shows orphan bone weight in viewport (ERROR icon row selected) ✓
3. Add weight on orphan bone → weight increases ✓
4. Scale weight on orphan bone → weight scales ✓
5. Smooth weight on orphan bone → weight smooths ✓
6. Sharpen weight on orphan bone → weight sharpens ✓
7. Scale orphan weight to 0 on all verts → entry removed from storage ✓
8. Orphan row disappears from bone list after weight = 0 ✓
9. Select real bone row → `active_orphan_name` cleared ✓
10. Real bone weight ops unaffected ✓
11. `SUPERSKIN_OT_select_orphan_bone_row` registers without error ✓
12. No duplicate class registration (removed from widget_deform_bones) ✓
