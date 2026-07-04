# 0025 — Mirror weight channel never gave true 50/50 weight to vertices sitting exactly on the mirror seam

**Date:** 2026-07-04
**Area:** `features/mirror/logic.py`

## Symptom

After mirroring the deform-bone weight (layer) channel, vertices sitting
exactly on the center of the model (the mirror plane itself) did not end up
with an even 50/50 split between the mirrored bone pair (e.g. `Leg.L` /
`Leg.R`) — they kept whatever one-sided weight they were originally
authored with (e.g. 100% `Leg.L`, 0% `Leg.R`), even after a successful
mirror.

A previous attempt to fix this regressed the self-intersecting-mesh
handling (the "oversized pant leg poking into the other leg" case
`classify_sides_by_topology()` exists for), and was reverted without a
proper root-cause fix.

## Root cause

`classify_sides_by_topology()`'s raw-coordinate fallback, and the Rust
`is_target`/`_raw_side` tests used throughout `apply()`/`rust_mirror_apply`,
classify a vertex as target-side using a strict `<` / `>` comparison against
`0`. A vertex whose coordinate is *exactly* `0` along the mirror axis (a
true center-seam vertex, common on a symmetric mesh's shared centerline edge
loop) always evaluates to source-side, never target-side. `apply()`'s
STEP 1 (clear target side) and STEP 2 (mirror source → target) both only
ever touch target-side vertices — so a center vertex is never cleared and
never receives the mirrored bone's weight. It simply keeps its original,
possibly one-sided, weight untouched.

## Why it wasn't obvious / why the first attempt regressed something else

The first fix attempt reused (or overlapped with) `classify_sides_by_topology()`'s
wide classification margin (15% of the mesh's own axis span — deliberately
wide so a *localized* self-intersecting bulge doesn't get misclassified) to
also decide which vertices count as "center." That wide margin is
appropriate for topology-based side classification, but is a completely
different concept from "is this vertex genuinely on the seam" — using it
for both purposes meant vertices *near* (but not on) the seam, including
ones affected by self-intersecting geometry, got pulled into the
symmetrization logic too, corrupting the self-intersection-safe
classification the margin exists for.

## Fix

`features/mirror/logic.py`:
- Added `_is_true_center_vertex()` — a strict test using a small, FIXED
  absolute epsilon (`_CENTER_EPSILON = 1e-4`), completely independent of
  `classify_sides_by_topology()`'s margin. This only ever matches vertices
  whose coordinate is genuinely ~0 along the mirror axis, never the wider
  "within classification margin" set.
- Added `_symmetrize_center_vertices()` — runs after `apply()`/
  `_fill_weight_gaps()`, entirely as a separate post-process over the
  already-computed result. For each true-center vertex and each mirrored
  bone pair, sets both bones to `(w_src + w_tgt) / 2.0` (skipping any pair
  where either bone is locked), then renormalizes via the same
  `rust_norm_all_unlocked` gateway `_fill_weight_gaps()` already uses.
- `execute_mirror_pipeline()` calls this once, right after the weight
  gap-fill step, on the final `res_layer_int` dict — before it's converted
  back to string bone names and written.
- No changes to `classify_sides_by_topology()`, `target_side_mask`,
  `apply()`/`rust_mirror_apply`, or any self-intersection-related code path
  — this feature is fully decoupled, by construction, from the topology
  classification the previous attempt broke.

## General lesson

When a fix needs to touch "vertices near/on a special line" (a seam, a
plane, a boundary), don't reuse an existing "is this vertex near that line"
classification that was tuned for a *different* purpose (here: tolerating
self-intersecting geometry) — the tolerance/margin that makes one check
correct for its own purpose can silently corrupt a second, unrelated check
built on top of it. Keep purpose-specific spatial tests independent, even
if it means writing a second, simpler version of a similar-looking check.
