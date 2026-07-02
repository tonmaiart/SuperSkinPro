> [RESOLVED 2026-07-02] `CoreFacade._locks_by_id()` in `core/facade/read.py` now
> covers every bone in the unified mapping, defaulting absent bones to `False`
> (unlocked), instead of only returning entries present in the per-layer
> `bone_locks` metadata.

# 0021 — Smooth/Sharpen silently no-op on any layer with no explicitly-locked bones

**Date:** 2026-07-02
**Area:** `core/facade/read.py`, `rust_logic/src/smooth_logic.rs`,
          `features/weight_apply/weight_apply_feature.py`

## Symptom

Pressing Smooth (with the whole mesh implicitly selected, no explicit vertex
selection) produced zero change on a given layer's weights, on every press, with
no error. Confusingly, Smooth worked correctly on the mesh's base/original layer,
but not on a newly created layer above it — same mesh, same action, same Rust
binary, different result depending only on which layer was active.

This was investigated as part of the same session as `docs/bug-history/0020`
(a real, separate mask-wipe bug on the same action). After 0020 was fixed and
confirmed via debug logging, this second, independent bug was still present and
needed its own root-cause trace.

## Root cause

`CoreFacade._locks_by_id()` (`core/facade/read.py`):

```python
def _locks_by_id(self) -> dict:
    name_locks = self._layer_mgr.get_bone_locks(
        self.storage.read_meta_list(), self.active_layer_index
    )
    bone_to_id, _ = self.storage.get_unified_mapping(self.obj)
    return {bone_to_id[name]: locked
            for name, locked in name_locks.items()
            if name in bone_to_id}
```

`name_locks` comes from `LayerCompositor.get_bone_locks()`, which reads the
per-layer `bone_locks` metadata field with a default of `{}`
(`_get_field(meta_list, layer_index, "bone_locks", {})`). This is correct and
intentional: a layer where no bone has ever been explicitly locked/unlocked has
an empty `bone_locks` dict — every other consumer of this data in the codebase
treats "absent from the dict" as "not locked", e.g.
`layer_crud.apply_bone_locks()`:

```python
locks = get_bone_locks(ctrl)
for item in ctrl.obj.superskin_bones_collection:
    item.lock_weight = locks.get(item.name, False)
```

`_locks_by_id()` was the one place that didn't follow this convention: instead of
defaulting missing bones to `False`, its dict comprehension only emits an entry
for bones that are *already keys* in `name_locks`. For a layer whose
`bone_locks` metadata is `{}` (any freshly created layer, or any layer where no
lock has ever been toggled), the returned dict is `{}` too — not "every bone
unlocked", but "no bones at all".

This dict is passed to Rust as `vertex_groups_lock`. `smooth_logic.rs` builds its
list of bones to process by filtering the dict's own *keys*, not by iterating a
separately-known bone universe:

```rust
let unlocked_vg_ids: Vec<i32> = vertex_groups_lock
    .iter()
    .filter(|&(_, &locked)| !locked)
    .map(|(&id, _)| id)
    .collect();
```

An empty `vertex_groups_lock` therefore produces an empty `unlocked_vg_ids`, and
every subsequent loop keyed off it (`for &vg_id in &unlocked_vg_ids`) does
nothing — the function returns `layer_dict` completely unmodified. This affects
`smooth` and `sharpen` (both iterate all unlocked bones this way); `add` and
`scale` were not visibly affected because they operate on a single
caller-supplied `active_vg_id` rather than iterating the lock dict's keys.

## How it was diagnosed

Confirmed by temporary debug prints added to `weight_apply_feature.execute()`
(see `docs/bug-history/0020` for the same instrumentation, added for that bug and
reused here) that compared `layer_int` vs `res_layer` per vertex after the Rust
call. The log showed `locks_id total=0 unlocked=0` and `0/2425 verts changed` on
the newly created layer, versus `locks_id total=67 unlocked=67` and
`775-1192/2425 verts changed` on the base layer of the same mesh in the same
session — isolating the variable to the per-layer lock dict rather than anything
mesh- or Rust-binary-specific.

## Fix

**`core/facade/read.py` → `CoreFacade._locks_by_id()`**
Changed to build the result over every bone in `bone_to_id` (the full unified
mapping), defaulting to `False` via `name_locks.get(name, False)` for any bone
not present in the per-layer `bone_locks` metadata — matching the existing
`.get(name, False)` convention already used by `apply_bone_locks()`.

## General lesson

A sparse "only lists exceptions" dict (here: `bone_locks`, which only needs to
list bones a user has actually toggled) is a reasonable storage format, but every
consumer must apply the same default when expanding it back to the full domain.
One consumer (`apply_bone_locks`) got this right; another consumer of the exact
same underlying data (`_locks_by_id`) got it wrong, and the failure mode was not
a crash or an obviously-wrong value — it was silent, total inaction, gated behind
"only on layers where the sparse dict happens to be empty," which made it look
layer-specific/mesh-specific rather than a straightforward missing-default bug.
When a Rust/FFI function derives its iteration domain from a dict's own keys
rather than from an explicitly passed-in universe, every Python-side producer of
that dict must be audited for "does this need to be dense, not sparse" — see
`docs/bug-history/0020` for the immediately preceding case, found in the same
debugging session, of a similar identity/completeness mismatch (`{}` vs `None`)
at the write side of the very same weight-apply pipeline.
