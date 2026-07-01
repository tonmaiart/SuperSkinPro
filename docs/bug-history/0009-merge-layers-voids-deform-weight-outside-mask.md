# 0009 — Merge Selected Layers voids deform-bone weight data outside mask

**Date:** 2026-06-19
**Area:** `core/layer_manager/compositor.py`

## Symptom

Merging two layers (Layers tab, multi-select → Merge Selected Layers) into
one target layer worked correctly for the resulting layer's *mask* — its
shape/coverage matched what the user expected from compositing the source
layers' masks. But the resulting layer's deform-bone *weight* data came out
empty ("void") in any area outside the topmost selected layer's painted mask
region, even though the lower selected layer clearly had real weight data
painted there before the merge. The user's expectation: outside the
overlay's mask, the merged layer's weight data should be identical to
whatever the lower layer originally had — nothing should be lost.

## Root cause

`merge_layers()` composites only the user-selected subset of layers via the
same algorithm `composite_layers()` uses for the full stack: process layers
bottom-to-top, the first (lowest) one with real data becomes the subset's
"foundation" (`is_base`), and the foundation's own weight is written as
`weight * its_own_mask_value`. For the *real* global foundation layer
(`"Base"`, created by `init_layer_system()` with no `mask_default` key at
all, so it falls back to `1.0`), that multiplication is a no-op — full mask,
full weight, everywhere.

But `merge_layers()` doesn't require the selected subset to include the real
"Base" layer. Any *ordinary* layer the user created via "+ New Layer" gets
`"mask_default": 0.0` baked into its metadata explicitly
(`LayerManager.create_layer`, `core/layer_manager/layer_manager.py:60`) —
new layers start fully transparent, like a new Photoshop layer, until
explicitly mask-painted. If the user never touched that layer's mask channel
at all (a very common case: they only ever painted weight in the Deform
Bones tab, which never writes to `ss_mask_N` — see
`core/layer_storage/storage_service.py`'s `save_active()`, only writes the
mask when `is_mask_mode=True`), that layer's effective mask is `0.0`
*everywhere*.

When such a layer ends up as the merge subset's `is_base`, its own weight
gets multiplied by `0.0` at every vertex the overlay layer doesn't cover.
The final per-vertex normalization step then divides by a near-zero total,
which either produces nothing or gets filtered out by the `> 0.001`
threshold — so the vertex silently disappears from the merged weight dict
entirely, even though real weight data existed for it going in. The
separate mask-coverage pass (`_composite_subset_coverage`) is unaffected
by any of this — it's a completely independent computation over the real
mask channel — which is exactly why the user observed "mask is fine, weight
is void": two different code paths, only one had the bug.

## Why it wasn't obvious / why a first attempt didn't catch it

- A first read of `composite_layers_vanilla()` / `layer_compositor.rs`
  looks correct in isolation: the foundation layer's mask multiplying its
  own weight is exactly right when the foundation really is "Base" (full
  mask). The bug only appears when the merge subset's *lowest selected*
  layer isn't the real global foundation — which is the common case for
  "merge two of my working layers together," not an edge case the original
  author was likely testing against.
- Differential fuzz-testing `composite_layers_vanilla()` against the real
  compiled Rust binary (`rust_composite_layers`) across thousands of random
  layer configurations showed **zero divergence** between vanilla and Rust
  for vertex presence/absence — confirming the underlying compositor
  algorithm itself is internally consistent and not Rust/vanilla skew. The
  bug is specific to how `merge_layers()` *uses* that algorithm for an
  arbitrary subset, not the algorithm itself.
- A naive fix (forcing the subset foundation's mask to `1.0` for the entire
  weight composite pass) initially looked right but actually changed blend
  *ratios* in regions where the overlay layer also partially covers —
  verified via a 5000-trial regression fuzz comparing old vs. new merge
  output, which caught dozens of cases where previously-correct blended
  values shifted. The real fix had to touch only vertices that were
  completely absent from the result, not reweight everything.

## Fix

`core/layer_manager/compositor.py`, `merge_layers()`: after computing
`weight_dict` via the normal `composite_layers()` call (unchanged), run a
backfill pass — decode the subset foundation layer's raw weight data
directly, and for any vertex `composite_layers()` left completely absent
from `weight_dict` (not just low-weight, genuinely missing), re-normalize
that vertex's raw weight from the foundation layer and insert it. Vertices
that already received any contribution (from the foundation at a meaningful
mask value, or blended with an overlay) are left exactly as
`composite_layers()` produced them, so masked-overlap blend ratios are
untouched. The mask-coverage pass (`_composite_subset_coverage`) is not
touched at all.

Verified via:
1. A targeted repro matching the reported scenario (two non-"Base" layers,
   lower one fully weight-painted but never mask-painted, upper one a
   small masked patch) — backfill correctly restores the lower layer's data
   outside the patch.
2. A 5000-trial regression fuzzer comparing old vs. new `merge_layers()`
   output across randomized layer/mask/weight configurations: the mask
   output is byte-identical in all 5000 trials, every previously-non-void
   weight value is byte-identical in all 5000 trials, and 590 trials show
   the fix correctly filling in previously-void vertices.

## How it was diagnosed

1. Read `merge_selected_layers()` (`core/ui_controller/layer_crud.py`) and
   `merge_layers()` / `composite_layers()` / `composite_layers_vanilla()`
   (`core/layer_manager/compositor.py`) to understand the full call chain.
2. Manually traced the alpha-blend algorithm for a simple 2-layer case
   (full-mask foundation + partial-mask overlay) — this case worked fine,
   which initially looked like it ruled out the compositor itself.
3. Differential-fuzz-tested `composite_layers_vanilla()` against the real
   compiled `rust_composite_layers` binary (loaded directly via
   `importlib`, with `bpy` and `RustGateway` stubbed out so the pure-Python
   modules could run outside Blender) across 3000+ randomized
   configurations — zero vertex-presence divergence, ruling out a
   Rust/vanilla skew as the cause.
4. Grepped every write site for `"mask_default"` across the codebase and
   found it's set to `0.0` in exactly one place
   (`LayerManager.create_layer`) and never flipped to `1.0` anywhere else
   for ordinary layers — only the literal "Base" layer's metadata omits the
   key entirely (implicit fallback to `1.0`).
5. Reproduced the exact void with a standalone script constructing a
   2-layer scenario where neither layer is "Base" — confirmed against the
   pre-fix code (loaded via `git show HEAD:...`) that vertices 1–3 came
   back as `None` in `weight_dict`.
6. Implemented and validated the fix with the targeted repro plus a
   5000-trial old-vs-new regression fuzzer (see Fix section).

## General lesson

In a layer-compositing system where "what counts as the foundation" is
relative to whatever subset is being processed (not always the literal
bottom of the whole stack), any per-layer property whose default value
depends on "is this layer the real foundation" (here: `mask_default`
defaulting to fully-transparent for ordinary layers, fully-opaque only for
the implicit literal foundation) needs explicit handling wherever a
*different* layer can temporarily play the foundation role — like a merge
across an arbitrary subset. Code that's correct for the full-stack case can
silently misbehave for a subset case without any exception, crash, or
Rust/vanilla divergence to flag it — the only signal is a quietly missing
vertex.
