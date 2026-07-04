# 0024 — Mirror mask gap-fill over-fills large regions to solid white on non-default-mask Layers

**Date:** 2026-07-04
**Area:** `features/mirror/logic.py`

## Symptom

Mirroring a mask with "Auto-Fill Gaps" enabled, on an asymmetric-topology
mesh, filled a large body region on the target side to fully solid white
instead of correctly reflecting mostly-empty coverage — reported directly by
a user after finally turning the gap-fill setting on for the first time.

## Root cause

`_fill_mask_gaps()` blended each gap vertex's fallback mask value from its
nearest triangle's 3 source vertices via:

```python
mask_val = sum(w * mask_dict_before.get(src_v, 1.0) for w, src_v in zip(bary, tri))
```

Hardcoding `1.0` as the fallback for any triangle vertex missing from the
sparse `mask_dict_before` dict assumes every Layer's implicit fill level is
fully painted. Per `docs/bug-history/0023` (an earlier fix to the exact same
class of bug, in the sibling `weight_transfer` domain), a missing mask-dict
entry does not mean "no coverage" — `get_active_mask_dict()` only returns
vertices explicitly painted *differently* from the Layer's own default fill
level. The real, effective value for a missing entry is the Layer's own
`mask_default` field, not a universal `1.0`.

For a Layer whose real `mask_default` is `0.0` (a "cutout"-style layer —
mostly unpainted, with a small explicit painted region), this hardcoded
fallback pulled every unpainted source triangle's contribution toward `1.0`
instead of `0.0`, blending large unpainted regions on the target side up to
solid white.

## Why it wasn't obvious

`_fill_mask_gaps()`'s own docstring cited `docs/bug-history/0023` as
justification for the `1.0` fallback, making it look like a deliberate,
already-reviewed decision rather than a bug — but 0023's actual fix was "read
the Layer's own `mask_default` field," not "always assume `1.0`." The mask
and weight channels in this domain are also known to require independent
side-classification logic (see this domain's README guardrail), which made it
easy to assume the mask channel's fallback-value choice was similarly
deliberate and isolated, rather than re-checking it against what 0023 actually
fixed.

## Fix

`features/mirror/logic.py`:
- `_fill_mask_gaps()` now takes a `mask_default: float` parameter and uses
  `mask_dict_before.get(src_v, mask_default)` instead of a bare `1.0`.
- `execute_mirror_pipeline()` looks up the active Layer's own `mask_default`
  via `core_facade.get_meta_list()` + `core_facade.get_active_layer_index()`
  (same pattern as `features/weight_transfer/ops.py`'s `_get_source_layers()`),
  falling back to `1.0` only if no meta entry matches the active index —
  matching `core/layer_storage/topology_heal.py`'s own default.

No Rust changes were needed — the barycentric blend happens entirely in
Python; the Rust side (`flat_bridge::flat_mirror_apply_mask`) only handles
clearing the target side, nearest-vertex matching, and gap detection.

## General lesson

A docstring citing a prior bug-history entry as justification is not proof
the citation is accurate — re-read the actual referenced fix before trusting
a comment's paraphrase of it, especially when the paraphrase conveniently
matches a hardcoded literal already sitting in the code.
