> [RESOLVED 2026-06-26] `read_temp_vgs_from_bm()` and the write path in `ui_controller.py` now
> read/write directly from the active BMesh deform layer. `weight_apply_domain.py` uses
> `core_facade.finish()` to guarantee `bump_deform_generation()` runs on every weight op.

# 0018 — Weight ops read stale temp VG data after 0016 undo redesign

**Date:** 2026-06-26
**Area:** `core/ui_controller/pipeline.py`, `core/layer_storage/temp_vg_bridge.py`,
          `core/ui_controller/ui_controller.py`, `features/weight_apply/weight_apply_domain.py`

## Symptom

After Add / Scale / Smooth / Sharpen in Edit Mode (via the `weight_apply`
domain), the GPU visualizer updated its colour heatmap correctly but the
armature-deformed mesh coordinates in the viewport remained frozen at the
pre-operation state. Exiting and re-entering skin mode caused the colours
to also snap back to the pre-operation values, confirming the data was never
actually persisted.

## Root cause

The `0016` undo redesign moved the active layer's source of truth during
Edit Mode from `ss_layer_N` ID properties to `__ssp_*` Vertex Groups, which
are tracked automatically by Blender's BMesh undo. This change introduced a
three-part mismatch in the weight-op pipeline:

**1. Read path read stale Object-mode data.**
`_read_active_layer_int()` in `ui_controller.py` still called
`storage.read_active_layer_dict()`, which reads `ss_layer_N`. After
`0016`, `ss_layer_N` for the active layer is written only on layer-switch
or Exit Edit Mode, so it reflects the state at the time the user entered
Edit Mode, not the current BMesh state.

**2. Flatten path also read stale data — and through the wrong API.**
`flatten_to_mesh_edit()` in `pipeline.py` called `update_from_editmode()`
followed by `read_temp_vgs_to_layer()`, which reads vertex group weights via
`mesh.vertices[i].groups`. While `update_from_editmode()` is documented to
copy the edit BMesh back to the mesh datablock, it does not reliably sync
vertex group (deform layer) data to `mesh.vertices` during Edit Mode
operations. Consequently, `read_temp_vgs_to_layer()` always returned the
state at Edit Mode entry, and the composite fed into bone VGs was always the
same — so the mesh never moved.

**3. Write path wrote to the wrong store.**
`_write_active_layer_string()` called `storage.save_active()`, which writes
to `ss_layer_N`. In the new architecture this is not the active-layer
source of truth during Edit Mode; `flatten_to_mesh_edit()` ignores
`ss_layer_N` for the active layer when temp VGs are present, so the write
had no effect on deformation. The shader colour update (which the user could
observe) originated from a separate read of `ss_layer_N` in the visualizer,
masking the fact that the bone VGs were never updated.

**4. Domain bypassed `CoreFacade.finish()` guarantee.**
`weight_apply_domain` called `ctrl._finish(color_only=True)` directly on
the raw `UIController` instead of going through `core_facade.finish()`.
The public facade wrapper is where `bump_deform_generation()` is guaranteed
to be called (per the `0010` fix), so bypassing it meant the topo/deform
cache was not invalidated even if the deformed coords had changed.

## Why it wasn't obvious

The colour heatmap updating correctly looked like "the write worked." In
reality, the visualizer's colour cache was reading from `ss_layer_N` (which
the old write path did update) while the deform-coordinate cache was reading
from the evaluated mesh (which depends on bone VGs, which were stale). The
two caches used different data sources, so they could diverge without any
Python exception. The `update_from_editmode()` + `mesh.vertices` pattern had
worked before `0016` (when temp VGs did not exist and the else-branch of
`flatten_to_mesh_edit()` read from `ss_layer_N` directly), so it was not
obvious that VG data from `mesh.vertices` was unreliable after the undo
redesign.

## Fix

**`core/layer_storage/temp_vg_bridge.py`**
Added two functions:
- `read_temp_vgs_from_bm(bm, obj)` — reads `__ssp_*` VG weights directly
  from a BMesh's deform layer, bypassing `mesh.vertices` entirely. Used by
  both the read and flatten paths.
- `write_layer_to_temp_vgs_bm(obj, mesh, layer_str, id_to_bone, mask_dict)`
  — writes a string-keyed layer dict back into `__ssp_*` VGs via the active
  edit BMesh's deform layer, making changes immediately visible to
  `flatten_to_mesh_edit()` without a `ss_layer_N` round-trip. Creates new
  `__ssp_*` VGs for any bone that gains weight for the first time in this
  edit session.

**`core/ui_controller/pipeline.py` → `flatten_to_mesh_edit()`**
Replaced `ctrl.obj.update_from_editmode()` + `read_temp_vgs_to_layer(obj)`
with `bmesh.from_edit_mesh(mesh)` + `read_temp_vgs_from_bm(bm_active, obj)`.
`bmesh.from_edit_mesh()` always returns a reference to the single active
edit BMesh; any changes made by the weight-op write path are immediately
visible here without any sync step.

**`core/ui_controller/ui_controller.py` → `_read_active_layer_int()`**
Added an Edit Mode branch: when temp VGs are present, reads directly from
the active BMesh via `read_temp_vgs_from_bm()` instead of reading
`ss_layer_N`. This ensures that consecutive weight ops within the same Edit
Mode session each see the result of the previous op, not the entry-state.

**`core/ui_controller/ui_controller.py` → `_write_active_layer_string()`**
Added an Edit Mode branch: when temp VGs are present, calls
`write_layer_to_temp_vgs_bm()` and returns early, skipping the
`storage.save_active()` call. `ss_layer_N` is intentionally not written
here; it is updated by the existing bake path on Exit Edit Mode or layer
switch (consistent with the `0016` design intent).

**`features/weight_apply/weight_apply_domain.py`**
Changed `ctrl._finish(color_only=True)` to `core_facade.finish(color_only=True)`
to restore the `bump_deform_generation()` guarantee from the `0010` fix.

## How it was diagnosed

Compared the pre-`0016` and post-`0016` flatten paths side by side.
Before `0016`, `flatten_to_mesh_edit()` had no `has_temp_vgs` branch — the
active layer was always read from `ss_layer_N`, which the domain also wrote
to, so the round-trip was consistent. After `0016`, the active layer source
of truth moved to the BMesh deform layer, but neither the read nor the write
path in the weight-op pipeline was updated to match. Confirmed by tracing
that the colour heatmap (which did update) was reading from `ss_layer_N`
while the deformation (which did not update) was sourced from the evaluated
mesh — two separate chains pointing at different stores. The reset on
exit/enter skin mode was the definitive indicator that `__ssp_*` VGs were
never written: the bake on exit preserved the entry-state, causing colours
to revert.

## General lesson

When moving the source of truth for a data structure (here: active layer
weights moving from `ss_layer_N` to `__ssp_*` BMesh VGs), every read and
write path that touches that data must be audited for the new store. A
secondary display path (the shader) that reads from the old store will
continue to update correctly, creating a false signal that the write
succeeded and delaying discovery of the broken primary path (deformation).
