# 0023 — Weight Transfer wrote zero vertices because a missing mask entry was treated as 0.0 instead of the layer's `mask_default`

**Date:** 2026-07-02
**Area:** `features/weight_transfer/ops.py`, `core/layer_storage/topology_heal.py` (source of the authoritative default)

## Symptom

While building a "closest point on surface" weight-transfer algorithm for the
`weight_transfer` domain (barycentric-blend both weight and mask from the
nearest source triangle), a source Layer with a mask filled solid white
transferred to the target with **zero vertices written** on the new Layer,
followed immediately by a full `Mask Gap Detected` warning covering every
target vertex — even though the debug log confirmed the source Layer's own
weight dict had real data (`source_layers=[('Base', 8)]`).

## Root cause

`CoreFacade.get_active_mask_dict()` only returns vertices that were
**explicitly painted differently** from the Layer's own default fill level.
A Layer whose mask was set to solid white via a "fill" action (rather than
painted vertex-by-vertex) never gets a dense per-vertex mask dict at all —
`get_active_mask_dict()` legitimately returns `{}`.

`_closest_surface_point_transfer()` blended each target vertex's mask value
from its nearest triangle's 3 source vertices via:

```python
mask_value += w * layer_mask.get(v_idx, 0.0)
```

Treating a missing dict entry as mask `0.0` silently zeroed out every
single vertex's mask contribution for a solid-white-filled Layer, since none
of its vertices ever appear as explicit dict keys. `mask_value` therefore
came out `<= 0.0` for every target vertex, and the `if mask_value <= 0.0: ...
continue` guard skipped writing *any* weight or mask data — producing a
Layer with 0 written vertices despite the source clearly having weight data.

The actual, authoritative fallback is **not** `0.0`. `core/layer_storage/
topology_heal.py` reads the same field as:

```python
mask_default = float(layer.get("mask_default", 1.0))
```

— i.e. a Layer's own `mask_default` (stored per-Layer in `ss_layers_meta`,
itself defaulting to `1.0` — "fully covered" — when even that key is
absent), not a global `0.0`.

## Why it wasn't obvious

The bug looked identical to an earlier, already-fixed issue in the same
function (forgetting to write mask data at all, or overwriting it with a
blanket `{v_idx: 1.0}` — see the domain's own README history). Because a
missing-dict-entry default of `0.0` is the intuitive assumption for "no data
== nothing here," and because `features/data_io/ops.py`'s own JSON
export/import path *also* independently assumes a `0.0` default for
`mask_default` (`layer_export.get("mask_default", 0.0)`) — a third stale
value in that file, on top of two previously-found bugs there
(`create_layer(visible=..., mask_default=...)` kwargs, and
`meta.get("slot", -1)` instead of `"index"`) — there was a second, wrong
"authoritative-looking" source pointing at the same incorrect default. Only
grepping `core/` directly for `mask_default` usage (rather than trusting
`data_io`'s prior art a third time) surfaced the real default in
`topology_heal.py`.

## Fix

`features/weight_transfer/ops.py`:
- `_get_source_layers()` now reads each Layer's own `mask_default` from its
  meta entry (`float(m.get("mask_default", 1.0))`) and returns it alongside
  `(name, weight_dict, mask_dict)` as a 4th tuple element.
- `_closest_surface_point_transfer()` takes `mask_default` as a parameter and
  uses `layer_mask.get(v_idx, mask_default)` instead of a bare `0.0`.

## General lesson

Don't trust a second file's "prior art" as independent confirmation of a
default value without checking whether both files could share the same root
cause — `data_io`'s `mask_default` handling had already been flagged as
stale twice in the same session for unrelated reasons, which should have
been a stronger signal to distrust it a third time rather than pattern-match
against it again. When a "missing key" default matters, grep the actual
read/write site inside `core/` for the literal field name — don't infer it
from a sibling `features/` file that reads the same JSON-ish shape for a
different purpose (export/import vs. live in-memory reads can drift
independently).
