# 0026 — Orphan bone's synthetic ID drifts once temp VGs exist, making its own `__ssp_N` VG invisible to writes

**Date:** 2026-07-07
**Area:** `core/layer_storage/geometry.py`, `core/facade/write.py`

## Symptom

After deleting/renaming an armature bone so its vertex group became orphaned
(weight data with no backing real VG), flooding a real bone's weight over
the orphan's territory in Edit Mode correctly increased the real bone's
weight (visible in the viewport), but the orphan's own weight in the
viewport color / `__ssp_N` temp VG never dropped to zero, no matter how much
was painted or how many times `_normalize_orphan_budget()` was invoked. The
orphan row also never left the Deform Bones list after Save Weights.

Direct instrumentation (see below) proved the *computed* result
(`layer_str`, the string-keyed dict about to be written) genuinely showed
the orphan's weight as fully zero every time — the bug was not in any
weight-math code path. Yet the live BMesh, checked independently via
Blender's own Python console immediately after the write, still held the
orphan's original weight at a fixed set of vertices.

## Root cause

`core/layer_storage/geometry.py::get_unified_mapping()` assigns each orphan
bone a synthetic int ID starting from:

```python
synthetic_id = len(obj.vertex_groups)
```

`obj.vertex_groups` includes **every** vertex group, real bones and
`__ssp_*` temp VGs alike, whenever an Edit Mode temp-VG session is active.
This makes the starting synthetic ID mode-dependent:

- At **Enter Edit Mode** (`_enter_edit_mode()` → `load_layer_to_temp_vgs()`),
  temp VGs don't exist yet, so `len(obj.vertex_groups)` is just the real
  bone count (e.g. 68). The orphan gets ID 68, and a VG literally named
  `__ssp_68` is created for it — landing at collection index 136 (real
  bones occupy 0–67, then one `__ssp_N` per bone — 68 more — occupy
  68–135, and the orphan's own temp VG, created last, lands at 136).
- **Mid-session**, `weight_apply_feature.py::snapshot_context()` calls
  `core_facade.get_unified_mapping()` again on every gesture. By now
  `obj.vertex_groups` also holds all the `__ssp_*` VGs (139 total in the
  reproduction case), so `len(obj.vertex_groups)` is 139, not 68 — the
  *same* orphan now gets synthetic ID **139**, not 68.

`write_layer_to_temp_vgs_bm()` resolves each `__ssp_N` VG's *bone name* by
parsing the `N` out of its name and looking it up in the `id_to_bone`
mapping it was handed (`id_to_bone.get(bone_vg_idx)`). With the mid-session
mapping now disagreeing with the ID baked into the VG's name at creation
time, `id_to_bone.get(68)` returns `None` for the VG literally named
`__ssp_68`. That VG is silently dropped from `ssp_vg_idx_map` /
`all_ssp_indices` — the write path's own bookkeeping of "which VGs am I
responsible for clearing/setting this call." Once a VG falls out of that
set, the clear-if-absent-from-new loop never even looks at it again, so its
weight is frozen at whatever it held at Enter Edit Mode time, forever,
regardless of what the (correctly computed) `layer_str` says.

## Why it wasn't obvious

Every diagnostic added along the way (see `write_active_layer_from_calc`'s
`core_pipeline` logging, and a dedicated `write_layer_to_temp_vgs_bm()`
post-delete verification pass) checked whether the *computed* result was
correct and whether the delete loop *did what it intended to do* — both
were true. Neither checked whether the loop's own scope
(`all_ssp_indices`/`ssp_vg_idx_map`) actually covered every `__ssp_*` VG
that existed on the mesh. The bug was an omission from that scope, not a
mistake within it, so scope-internal verification always came back clean.

Two earlier, superficially similar fixes in this same debugging session
(`core/facade/write.py`'s `known_bone_names`/`orphan_names_in_mapping`
computation, and `core/bone_identity/bone_identity_service.py`'s
`_mapping_has_orphan_ids`) had already hit the identical
"`len(vertex_groups)` is inflated by temp VGs" class of bug and were fixed
correctly — but `get_unified_mapping()` itself, the one place that actually
*assigns* the orphan's ID in the first place, still had it. Fixing the
*consumers* of a bad ID assignment does not fix an *unstable* ID assignment
upstream.

## How it was diagnosed

1. Added `core_pipeline` logging in `write_active_layer_from_calc()` to
   print the orphan's total weight in `layer_str` before/after
   `_normalize_orphan_budget()` + `prune_zero_bones()` — confirmed the
   computed result was correctly zero.
2. Added a `temp_vg`-gated post-delete verification pass directly inside
   `write_layer_to_temp_vgs_bm()`: re-scan the BMesh immediately after the
   clear/set loop and compare actual per-`__ssp_` vertex counts against
   what `new_weights` expected — came back with zero mismatches, meaning
   the loop faithfully executed its own (incomplete) scope.
3. Ruled out every intervening Python code path between the verified-clean
   write and the later Exit-Edit-Mode bake (`flatten_to_mesh_edit()`,
   `_get_visible_influence_bones()`, `preview_orphan_weight()`) by re-testing
   with each interaction removed one at a time — the residual data
   persisted regardless, isolating the cause to something the BMesh itself
   held, not a later Python write.
4. Decisive step: asked for a direct Blender Python console check, bypassing
   all of this addon's own code —
   `dict(bm.verts[V][bm.verts.layers.deform.active])` on one of the
   affected vertices, run once right after the scale and once after
   re-entering Edit Mode following Save. Both times the dict had **no**
   entry for gi 68, but carried a persistent nonzero entry at gi 136 (value
   identical across both checks) — a `__ssp_*`-range index never mentioned
   in `all_ssp_indices`'s own logged contents. That mismatch (68 named vs.
   136 actual, both unaccounted for by the write path's own bookkeeping)
   pointed directly at `get_unified_mapping()`'s ID assignment.

## Fix

**`core/layer_storage/geometry.py::get_unified_mapping()`**

```python
synthetic_id = len(bone_to_id)  # was: len(obj.vertex_groups)
```

`bone_to_id` at that point is already filtered to real (non-`__ssp_*`)
vertex groups, so `len(bone_to_id)` is the real bone count regardless of
whether temp VGs currently exist — the same value at Enter Edit Mode and on
every later mid-session call, so an orphan's synthetic ID (and therefore
its `__ssp_N` VG name) stays consistent for the entire session.

## General lesson

Any place that derives a count or index from `obj.vertex_groups` directly
must ask whether Edit Mode temp VGs could be loaded when it runs — if so,
filter to non-`__ssp_*` names/count explicitly, every time, even in code
that "only assigns an ID once." An ID-assignment function being called
more than once per session with a different result each time is a bug
class of its own, independent of whatever consumes that ID — fixing
downstream consumers to defensively re-derive the *same kind* of count
(as happened twice earlier in this same investigation) treats the symptom
without preventing a fresh instance of the actual defect from appearing
anywhere else `get_unified_mapping()` is called mid-session.
