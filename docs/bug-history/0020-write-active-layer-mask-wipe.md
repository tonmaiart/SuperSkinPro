> [RESOLVED 2026-07-02] Two independent bugs in `core/layer_storage/temp_vg_bridge.py`
> and `core/facade/write.py` both caused the same symptom. Both are fixed — see
> "Fix" below. The first fix alone (`{}` → `None`) did **not** resolve the visible
> symptom; the second fix (`all_ssp_indices` scope) is the one that actually stops
> the mask from being wiped.

# 0020 — Layer mask silently wiped on every weight op in Edit Mode

**Date:** 2026-07-01 (bug 1 fixed), 2026-07-02 (bug 2 found and fixed)
**Area:** `core/facade/write.py`, `core/layer_storage/temp_vg_bridge.py`,
          `features/weight_apply/weight_apply_feature.py`

## Symptom

In Edit Mode, performing any ordinary weight edit (Add, Scale, Smooth, Sharpen —
i.e. any action that is not itself editing the mask) on a layer that already had a
saved mask caused that mask to be cleared to empty. The weight edit itself applied
correctly; only the mask was destroyed, and it happened on the very first action,
every time, not just for Smooth.

## Root cause 1 (fixed 2026-07-01, insufficient on its own)

`WriteFacadeMixin.write_active_layer()` in `core/facade/write.py` called:

```python
self._write_active_layer_string(result_int, self._id_to_bone, {}, is_mask_mode=False)
```

passing a literal empty dict `{}` for the `mask_dict` argument. In Edit Mode with
temp VGs present, `_write_active_layer_string()` forwards this into
`write_layer_to_temp_vgs_bm()`, whose explicit mask-sync block:

```python
if mask_dict is not None and mask_vg_idx is not None:
    for bv in bm.verts:
        ...
        elif mask_vg_idx in v_deform:
            del v_deform[mask_vg_idx]
```

treats `{}` (which is `is not None`) as "the authoritative, complete mask state,"
and deletes the mask VG entry for every vertex. Fixed by passing `None` instead of
`{}`, matching the existing correct pattern in `write_active_layer_from_calc()`.

**This fix alone did not resolve the user-visible bug.** The user re-tested after
this fix (and independently, a Gemini-assisted analysis arrived at the exact same
diagnosis and fix) and the mask was still being wiped on every weight op. That led
to root cause 2 below, found by instrumenting `write_layer_to_temp_vgs_bm()` with
debug prints and re-reading the function line by line rather than assuming the
first fix was complete.

## Root cause 2 (the actual live bug) — `mask_vg_idx` leaking into the bone-weight clear scope

`write_layer_to_temp_vgs_bm()` (`core/layer_storage/temp_vg_bridge.py`) builds a
"clear-if-absent" scope for the **bone weight** sync loop:

```python
mask_vg_idx = mask_vg.index if mask_vg is not None else None

all_ssp_indices: set = set(ssp_vg_idx_map.values())
if mask_vg_idx is not None:
    all_ssp_indices.add(mask_vg_idx)          # <-- bug: mask index in the wrong scope

...
new_weights: dict = {}
for v_idx, bone_weights in layer_str.items():
    entry: dict = {}
    for bone_name, w in bone_weights.items():
        gi = ssp_vg_idx_map.get(bone_name)     # bone-name -> vg index; NEVER mask_vg_idx
        if gi is not None and float(w) > 0.0:
            entry[gi] = float(w)
    new_weights[int(v_idx)] = entry
# new_weights (and therefore `new` below) can structurally never contain mask_vg_idx

for bv in bm.verts:
    v_deform = bv[deform]
    new = new_weights.get(bv.index, {})
    for gi in list(v_deform.keys()):
        if gi in all_ssp_indices and gi not in new:
            del v_deform[gi]                   # <-- fires for mask_vg_idx on EVERY vertex, EVERY call
    for gi, w in new.items():
        v_deform[gi] = w
```

`all_ssp_indices` includes `mask_vg_idx` (added a few lines above so the mask VG
counts as "temp-VG owned" for other purposes), but `new_weights` — built purely
from `layer_str`'s bone names via `ssp_vg_idx_map` — can **never** contain the
mask VG index. So on every single call to `write_layer_to_temp_vgs_bm()`, the
bone-weight sync loop sees `mask_vg_idx in all_ssp_indices and mask_vg_idx not in
new` for every vertex and deletes the mask VG entry — completely independent of
the `mask_dict` argument, and independent of the `{}` vs `None` fix from root
cause 1. This is why that first fix produced no visible change: it correctly
disabled the *explicit* mask-sync block, but the *bone-weight* sync loop above it
was clearing the same data unconditionally, every time, before the mask block
even ran.

Confirmed via debug instrumentation (temporary `print()` calls added to
`write_layer_to_temp_vgs_bm()`, `_write_active_layer_string()`, and
`weight_apply_feature.execute()`) and by static trace of the set/dict logic —
both agree independently.

## Why it wasn't obvious

The first fix ({} → None) *looked* complete: it was the fix an independent
re-analysis (by a different LLM, from scratch) also converged on, using the same
line of reasoning. Both analyses stopped at the first plausible mechanism that
produced the right symptom, without verifying that no *other* code path in the
same function could produce the identical symptom through an unrelated route. The
two bugs live in the same function, both fire on every Edit-Mode weight write,
and both delete the same VG entry — so there was no way to tell from behavior
alone that fixing one still left the other active. Only reading the bone-weight
loop's set membership logic line-by-line (or instrumenting it and watching the
count) revealed the second, independent cause.

## Fix

**`core/facade/write.py` → `write_active_layer()`**
Pass `None` instead of `{}` as the mask argument to `_write_active_layer_string()`.

**`core/layer_storage/temp_vg_bridge.py` → `write_layer_to_temp_vgs_bm()`**
Removed `mask_vg_idx` from `all_ssp_indices` — that set now only ever contains
bone-weight temp VG indices (`ssp_vg_idx_map.values()`), so the bone-weight sync
loop no longer has any way to touch the mask VG. The mask VG's lifecycle is now
governed exclusively by the explicit `if mask_dict is not None:` block below it,
as originally intended.

## General lesson

When two loops in the same function both claim "ownership" of overlapping state
(here: a shared `all_ssp_indices` cleanup scope used by a loop that only knows
about bone weights, plus a separate loop that only knows about mask), a bug in
either one can produce the identical externally-visible symptom. Fixing the loop
that *looks* responsible (the one with an explicit `mask_dict` check) is not
sufficient evidence that the *other* loop isn't also touching the same data by
accident — audit every loop that iterates the same set/scope, not just the one
whose guard condition matches the symptom's name. See `docs/bug-history/0019` for
a related case where a different escape-hatch write path was still on the
pre-redesign store even after the "obvious" one was fixed.
