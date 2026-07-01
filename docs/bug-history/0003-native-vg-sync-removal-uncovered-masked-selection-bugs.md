# 0003 — Native vertex-group sync removal uncovered masked selection-tracking bugs

**Date:** 2026-06-18
**Area:** `ui/__init__.py`, `core/data_models.py`, `operators/ops_interface.py`, `operators/ops_shortcuts.py`, `core/ui_controller/layer_crud.py`, `core/ui_controller/pipeline.py`, `core/shaders/bone_mode.py`, `core/shaders/deform_bone_overlay.py`

## Symptom

No user-visible symptom triggered this — it surfaced during an unrelated cleanup request (remove a no-longer-needed depsgraph handler that synced native `vertex_groups.active_index` into SuperSkinPro's own selection storage, since the workflow never touches the native Vertex Groups panel). While auditing every place that read or wrote native `vertex_groups.active`/`active_index` to decide what to do with the removal, two separate latent inconsistencies turned up in `obj.superskin_storage.last_clicked_index` tracking that had been invisible up to that point.

## Root cause (two distinct issues found during the same audit)

**1. Typo in the removed sync handler's guard property.** `superskin_active_sync_handler` (formerly in `ui/__init__.py`) compared `native_active_idx` against `storage.previous_active_index`, but on a match it wrote `storage.previous_active_idx` (missing the `ex`) — a different attribute name entirely. The real `previous_active_index` property was therefore never updated, so the guard's `!=` comparison stayed true on essentially every depsgraph update once the two diverged, meaning the handler likely re-ran its full clear-and-rebuild-selection logic far more often than the checksum-style guard was meant to allow. This was never root-caused at runtime (no traceback was ever reported) because the whole handler — and the `previous_active_index`/`suppress_sync` properties that existed solely to support it — was deleted outright as part of the same task, rather than patched.

**2. `SUPERSKIN_OT_select_vertex_group_row` tracked `storage.last_clicked_index` inconsistently with native `vertex_groups.active_index`, and native's correct behaviour was masking it.** Two of the four selection branches in `invoke()` had bugs in how they updated `last_clicked_index`:
   - The shift-range-select branch never updated `storage.last_clicked_index` at all — only the native pointer (`obj.vertex_groups.active_index = self.index`). As long as something else (`_active_vg_id()`, the GPU visualizer) read the native pointer for "what's active," this didn't matter.
   - The ctrl-click *deselect* branch set `storage.last_clicked_index = self.index` unconditionally — i.e. to the vertex-group index that had *just been removed* from the selection — while the native line two lines above it correctly fell back to `hist[-1] if hist else self.index` (the *previous* bone in history). Native quietly did the right thing; storage quietly recorded the wrong thing.

Neither bug had any visible effect because every consumer that mattered (`UIController._active_vg_id()`, `bone_mode.py`'s `dispatch_compute_colors`/`make_color_key`, `pipeline.save_current_layer_state()`) read from native `vertex_groups.active`, not from `storage.last_clicked_index`. The storage field was, until this point, write-only noise that nothing downstream actually consumed for decision-making.

## Why it wasn't obvious

This is the inverse of the usual "silent bug" shape: the bugs were *already silent* before anyone went looking, because the system had two parallel trackers of "the active bone" (native, and `storage.last_clicked_index`) and only one of them — native — was ever load-bearing. Inspecting `select_vertex_group_row` in isolation, both branches look like ordinary selection-state bookkeeping; nothing flags them as broken because the actual behaviour the user experiences (which row highlights, which bone gets painted) was always driven by the *other* tracker. The bugs only became load-bearing — and therefore visible as a real risk — once a deliberate architectural decision was made to retire native as the source of truth and promote `storage.last_clicked_index` to be the only one. Without that decision forcing a full audit of every native read/write site, these two branches could have shipped broken indefinitely.

## Fix

Removed the sync handler, `previous_active_index`, and `suppress_sync` outright (no longer needed once nothing reads native back into storage). Promoted `obj.superskin_storage.last_clicked_index` to be the single source of truth for "the active vertex group" everywhere: `UIController._active_vg_id()`, `bone_mode.py`'s SINGLE/MULTI color computation and cache-key generation, per-layer active-bone save/restore (`pipeline.save_current_layer_state` / `restore_layer_state`, `layer_crud.apply_active_bone`), the bone-list `template_list` row-highlight binding, the bone picker's hover/sweep/cancel paths, and the two "jump to this bone" popup operators (`OBJECT_OT_mw_select_specific_vertex_group`, `MESH_OT_show_affect_bone`) — all now read/write `last_clicked_index` exclusively. While doing so, fixed both branch bugs above: the shift-range branch now also sets `storage.last_clicked_index = self.index`, and the ctrl-deselect branch now sets `storage.last_clicked_index = hist[-1] if hist else self.index` to match what native used to do correctly.

## How it was diagnosed

Not diagnosed via debugging a live symptom — found by systematically grepping every call site that touched `vertex_groups.active` / `vertex_groups.active_index` as part of planning the native-dependency removal, then manually comparing, branch by branch, what native was doing versus what `storage.last_clicked_index` was doing in the same code path. The mismatch in the ctrl-deselect branch only became apparent by reading the two adjacent lines side by side; it would not have been caught by a behavioural test of the *current* code (since native masked it), only by this kind of "what would happen if this were the only source of truth" line-by-line audit.

## General lesson

When two parallel mechanisms track the same logical piece of state and only one of them is actually consumed, the unconsumed one can silently drift wrong for an arbitrary length of time — there is no test, manual or automated, that will catch it while it stays unconsumed, because nothing depends on it being correct yet. Before retiring whichever mechanism *was* load-bearing in favour of the other, audit every site that writes the soon-to-be-promoted one as if it already were the only source of truth, not just the sites that already read it. Also: don't introduce a second tracking property "just in case" without an explicit plan for which one is authoritative — `last_clicked_index` existed for a long time before this work without a clearly documented owner, which is exactly how issue (2) above went unnoticed.

A follow-up pass caught one more site after the initial fix shipped:
`deform_bone_overlay.py`'s draw callback also read native
`vertex_groups.active` directly to decide which bone to render in red
(the "active" wedge colour) — this file's source wasn't available
during the original audit. It now reads
`obj.superskin_storage.last_clicked_index` the same way every other
consumer does.
