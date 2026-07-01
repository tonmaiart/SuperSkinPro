> [ARCHITECTURAL UPDATE 2026-06-26] The deform-generation bump is now called unconditionally inside
> `pipeline.finish()` on both the `color_only` and full paths. The `@skin_transaction` decorator
> guarantees `_finish()` runs on every decorated operation, covering this invariant automatically.

# 0010 — `color_only` invalidate left the visualizer drawing weight-driven deformation at stale coordinates

**Date:** 2026-06-19
**Area:** `core/shaders/visualizer_base.py`, `core/shaders/bone_mode.py`, `core/shaders/mask_mode.py`, `core/shaders/shader_manager.py`, `core/ui_controller/pipeline.py`, `core/ui_controller/layer_crud.py`

## Symptom

After Add / Scale / Smooth / Sharpen / Mirror, the GPU weight-paint visualizer
(wireframe, selection dots, weight-colour triangles) did not visibly update —
it looked frozen at the pre-operation state. Auto Assign was unaffected. The
only reliable workaround was scrubbing the timeline (any frame change), which
immediately snapped the visualizer to the correct, current state.

## Root cause

`visualizer_base.make_draw_callback()`'s per-frame staleness check splits
into three independent caches (`topo_cache`, `sel_cache`, `col_cache`), each
keyed by a tuple built from `(obj, bm, deformed_key)`, where
`deformed_key = context.scene.frame_current`. `topo_cache` stores not just
mesh topology (vert/edge/face counts) but also `coords_3d` — the
Armature-evaluated, deformed vertex positions, extracted once via
`extract_deformed_coords()` and reused by the wireframe, selection-point, AND
colour-triangle batches.

`pipeline.finish(color_only=True)` (used by all six weight-mutating macro
ops except `auto`) explicitly invalidates *only* `col_cache`, leaving
`topo_cache` — and therefore `coords_3d` — untouched, on the documented
assumption that "topology hasn't changed" for a weight-paint stroke. That's
true for vert/edge/face counts, but false for the *deformed shape*: every one
of these ops flattens its result onto the mesh's real Vertex Groups, which is
exactly the input the Armature modifier deforms against. At a fixed
`frame_current`, a weight change reshapes the evaluated mesh just as much as
moving the timeline does — `topo_key` simply had no way to see it, because
`frame_current` was its only signal for "has the deformed shape changed."

The colour batch *did* get correctly recomputed with fresh weight data (its
cache was properly nulled), but it was drawn using the stale `coords_3d` from
before the operation — so visually nothing appeared to move or recolor in
step with the edit. `switch_to_layer()` (`core/ui_controller/layer_crud.py`)
had the identical issue: it reflattens onto a different layer's composite
(also a real-weight change) and only called the colour-only refresh.

`auto()` was unaffected because it calls `_finish()` with the default
`color_only=False`, which fully invalidates `topo_cache` and forces a fresh
`coords_3d` extraction every time — masking the underlying gap rather than
revealing it.

## Why it wasn't obvious

The bug looks exactly like "the colour cache didn't get cleared," which is
the very failure mode `docs/bug-history/0007` describes fixing — but that
diagnosis is wrong here. The colour cache *was* clearing correctly every
time; the actual staleness was in position data that the colour-only path
was never designed to touch. The `topo_cache` docstring even hints at the
real scope ("topology/deform cache key") but the only field actually feeding
that "deform" half was `frame_current`, which only catches animation-driven
deformation, not weight-driven deformation at a fixed frame. Nothing in the
explicit `invalidate_color_only()` call chain raises an error or warning —
the rebuild happens, just against the wrong positions, so there's no
exception to trace, only a visual lag whose root mechanism is one cache
dictionary away from where the symptom (color) points.

## Fix

Added a cheap, explicit "deform generation" counter
(`core/shaders/visualizer_base.py`: `bump_deform_generation()` /
`get_deform_generation()`) instead of reverting `color_only` ops back to a
full invalidate (which would have undone the perf win from `0007` and added
unnecessary full-topology rebuilds — `bm.calc_loop_triangles()` and the full
wireframe edge list — to operations that don't need them).

1. `BoneMode.make_topo_key()` / `MaskMode.make_topo_key()` now include
   `visualizer_base.get_deform_generation()` in their cache-key tuple, so a
   bump alone is enough for the existing self-detecting key-diff mechanism
   (the same mechanism `0007` relied on for `active_vg_id` changes) to mark
   `topo_cache` stale and re-extract `coords_3d` on the next draw.
2. `pipeline.finish()` calls `ctrl.shader_mgr.bump_deform_generation()`
   unconditionally, right after every flatten, before either invalidate
   branch — every weight-mutating op already routes through this one choke
   point, so nothing in `operations.py` had to change.
3. `layer_crud.switch_to_layer()` — the one other place that reflattens real
   weights and calls a colour-only refresh — got the same bump added
   directly, since it doesn't go through `pipeline.finish()`.
4. The bump was deliberately **not** folded into
   `ShaderManager.invalidate_color_only()` itself, because that method is
   also called from the high-frequency, non-deform-changing paths `0007`
   optimized (`_deferred_invalidate()`'s depsgraph catch-all, bone-hover,
   layer-switch selection state, ramp-preference changes in
   `ops_preferences.py`). Bumping there would have silently reintroduced the
   exact hover/select lag `0007` fixed, just via a generation counter
   instead of a full invalidate.

## How it was diagnosed

Traced the one real behavioural difference between the broken five ops and
the working `auto()`: both call `pipeline.finish()`, differing only in the
`color_only` flag. Read `invalidate_color_only()` vs `invalidate_and_redraw()`
side by side and confirmed the explicit colour-cache reset *should* force a
correct colour rebuild on the next draw regardless of the `color_key`
formula — ruling out "colour cache key doesn't include weight data" as the
actual cause, even though that's also true and looks like the obvious
culprit at first read. Re-read `build_topo_batches()` and noticed `coords_3d`
is shared by the wireframe, selection points, AND colour triangles, and that
`color_only` mode reuses `topo_cache["coords_3d"]` unconditionally. Connected
that to the user's workaround (scrubbing the timeline) being the one action
that forces `topo_key` — not `color_key` — to change, which is what actually
re-extracts `coords_3d`.

## General lesson

When a "topology" cache also smuggles in non-topology state (here: deformed
*coordinates*, which depend on live weight data, not vertex/edge/face
counts), a "this didn't touch topology" invalidation shortcut can be wrong
in a way that's invisible from the shortcut's own code — the bug shows up in
a *sibling* cache that happens to read from the same dict. Audit what a
cache dict actually stores, not just what its variable name implies, before
trusting an invalidation split made on the name's assumption.
