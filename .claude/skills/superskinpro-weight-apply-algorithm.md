---
name: superskinpro-weight-apply-algorithm
description: Use this skill for ANY task touching the algorithmic/mathematical internals of features/weight_apply/ — Add/Scale/Smooth/Sharpen math, the smooth_across_surface geodesic-neighbor mode, the sharpen checkerboard-divergence fix, the Alt+LMB/Alt+RMB gesture modal's interaction mechanics, or the dirty_verts performance-optimization pattern threaded through core/ and core_subsystems/ for this domain's hot path. Trigger on "weight apply algorithm", "smooth across surface", "sharpen checkerboard", "gesture shortcut", "weight_gesture", "dirty_verts", "gesture lag/laggy/หน่วง", or any request to modify apply_action()/logic.py's Rust-call math, ops.py's modal operator, or the compositor's dirty_verts/COO/cache optimization path. This is a knowledge/lessons-learned skill, not a scaffolding skill — use superskinpro-domain for generic new-domain creation and superskinpro-core-debug for unrelated core bugs.
---

# SuperSkinPro — Weight Apply Algorithm & Performance Skill

Consolidated knowledge from the session that added `smooth_across_surface`,
fixed the sharpen checkerboard bug, redesigned the gesture shortcuts, and ran
a multi-round performance-optimization campaign on the weight-apply gesture.
Read `features/weight_apply/README.md` first (per `superskinpro-locate`) for
the current, authoritative action/write-path spec — this skill exists for
the *why*, the *history of what was tried*, and the *pitfalls*, which don't
belong in that README's day-to-day contract documentation.

---

## Action Math Quick Reference

| Action | Rust function | Core behavior |
|---|---|---|
| `add` | `rust_add_logic`(via `apply_add`) | Adds intensity to the active bone's weight at each selected vertex, renormalizing others. |
| `scale` | `rust_scale_logic` (via `apply_scale`) | Multiplies the active bone's weight by intensity. |
| `smooth` | `rust_smooth_logic` (via `apply_smooth`) | Averages weights across a neighbor set (see below for which one). |
| `sharpen` | `rust_sharpen_logic` (via `apply_sharpen`) | Pulls weight toward the center vertex, away from its neighbor average (contrast enhancement). |

All four are dispatched from `features/weight_apply/weight_apply_feature.py::apply_action()`,
which never mutates its `ctx` snapshot — safe to call repeatedly at different
intensities from the same baseline (this is what makes gesture live-preview
possible without compounding).

---

## Smooth Across Surface (geodesic neighbor widening)

`smooth_affected_only` and `smooth_across_surface` are independent toggles:
the former filters *which vertices* get touched, the latter changes *which
neighbors* count toward each vertex's average — do not conflate them when
extending either.

- Plain smoothing uses `core_facade.get_cached_mesh_neighbors()` (1-ring
  adjacency) — effective smoothing radius is tied to hop count, so dense
  topology smooths slower per unit distance than sparse topology.
- `smooth_across_surface` routes through `logic.py::build_surface_neighbors()`
  instead: bounded BFS over the same 1-ring adjacency graph, accumulating
  edge length as an approximate geodesic distance, producing an expanded
  `{v_idx: [neighbor_idx, ...]}` map sized to a comparable real-world radius
  regardless of local topology density.
- This map is a drop-in replacement for the raw 1-ring neighbors argument to
  the exact same `rust_smooth_logic` FFI call — no Rust/core changes needed
  for this toggle, only the Python-side `neighbors` argument's shape.
- Results are cached in `_SURFACE_CACHE` (`logic.py`), keyed on mesh identity
  **plus `radius_multiplier`/`max_hops`**. This key was originally missing
  the radius/hops component — smooth (default radius `3.0`) and sharpen
  (`SHARPEN_RADIUS_MULTIPLIER = 2.0`) silently shared/corrupted each other's
  cached neighbor sets once sharpen started reusing the same function. If
  you add a third caller of `build_surface_neighbors()` with yet another
  radius, re-verify this cache key still includes every parameter that
  changes the returned map's shape.

---

## Sharpen Checkerboard Divergence — Root Cause & Fix

**Symptom:** repeated Sharpen presses caused isolated per-vertex weight
spikes ("checkerboard") instead of cohesive ring/zone divergence, eventually
destroying the weight distribution.

**Root cause:** plain 1-ring adjacency (`get_cached_mesh_neighbors()`) is
often only 4-6 vertices. `rust_sharpen_logic` pulls each vertex's weight away
from its neighbor average — with a tiny neighbor set, a single already-
saturated (0.0 or 1.0 clamped) neighbor dominates that average, and repeated
presses cascade the saturation vertex-by-vertex in a checkerboard pattern
rather than smoothing outward as a cohesive zone.

**Fix:** `sharpen` always feeds `build_surface_neighbors(..., radius_multiplier=
SHARPEN_RADIUS_MULTIPLIER)` (currently `2.0`) instead of the raw 1-ring
neighbors — widening the neighborhood dilutes any single saturated vertex's
influence on the average. This is unconditional (no checkbox) since the
tight 1-ring average was the bug itself, not a legitimate alternate mode.
The Rust formula in `rust_sharpen_logic` itself was never touched — this was
a pure neighbor-set-shape fix on the Python side.

**If sharpen ever regresses to checkerboard behavior again:** check whether
something changed `SHARPEN_RADIUS_MULTIPLIER`, changed the sharpen call site
to bypass `build_surface_neighbors()` back to raw 1-ring, or whether the
`_SURFACE_CACHE` key regressed to not including `radius_multiplier` again
(see above).

---

## Gesture Modal Mechanics (`SUPERSKIN_OT_weight_gesture`, `ops.py`)

- **Combined signed-axis design**: Alt+LMB = `add_scale` (positive drag →
  Add, negative → Scale via `1.0 + v`), Alt+RMB = `smooth_sharpen` (positive
  → Smooth, negative → Sharpen via `-v`). `_COMBINED_RESOLVERS` maps the sign
  to `(real_action, intensity_fn)`. This was an explicit user redesign away
  from separate per-action shortcuts — do not "simplify" it back to 4
  separate bindings without confirming that's actually wanted again.
- **Hold-only, no plain-click apply**: a click that never crosses the drag
  threshold does nothing (no write, no undo step). This was also an explicit
  redesign (removing an earlier click-to-apply-once behavior) — do not
  reintroduce a click-apply path without confirming.
- **`self._trigger_type = event.type`** captured at `invoke()`, matched
  against at release — never hardcode `event.type == 'LEFTMOUSE'`/`'RIGHTMOUSE'`
  for release detection. This bit `circle_tool_adjust` and `bone_picker`'s
  modals when their keymap bindings moved to different mouse buttons during
  this same redesign (their modals never terminated because they checked a
  hardcoded button that was no longer the trigger). Any new modal operator
  in this codebase bound to more than one possible mouse button needs this
  pattern from day one.
- **`cursor_warp` infinite-drag accumulation gotcha**: `self._drag_value`
  must be updated as `max(-1.0, min(1.0, self._drag_value + delta *
  sensitivity))` — an **accumulating** running value — never recomputed
  fresh each frame as `delta * sensitivity` from the press position. Because
  `cursor_warp()` resets the mouse position every frame, a "recompute from
  absolute offset" implementation caps the reachable range at whatever a
  single event's movement can produce (was measured at ~0.03-0.04 before the
  fix). This is the same accumulation trick `CircleToolAdjust` already used
  (`prefs.brush_radius_value + delta`) — follow that precedent for any new
  infinite-drag modal.
- **Timer-throttled apply, not per-`MOUSEMOVE`**: `MOUSEMOVE` only updates
  `self._drag_value` (cheap). A `TIMER` event at `_GESTURE_APPLY_INTERVAL`
  (currently `1.0/60.0`, was `1.0/30.0`) is what actually calls `self._apply()`.
  This decouples "how fast the mouse reports movement" from "how often the
  expensive Rust+flatten pipeline runs" — the single highest-leverage,
  zero-regression-risk performance change made this session. Don't remove
  the timer gate to "feel more responsive" without re-measuring; per-`MOUSEMOVE`
  apply was the original, much-laggier design.
- **No mid-gesture cancel by design**: no ESC/cancel branch. Release always
  commits; reverting is Ctrl+Z only. This is intentional, not an oversight.

---

## The `dirty_verts` Performance Pattern (and its correctness trap)

This pattern was threaded through `features/weight_apply/weight_apply_feature.py`,
`core/facade/write.py`, `core/ui_controller/pipeline.py`,
`core/layer_storage/temp_vg_bridge.py`, and the Rust compositor, to make the
gesture's per-tick cost scale with brush size instead of total mesh size.
**The single rule that matters if you touch any of this again:**

> `dirty_verts` may ONLY restrict which vertices a loop **iterates**. It must
> NEVER restrict what data a "read the current complete state" call receives,
> because multiple functions on this path treat "key absent from the dict" as
> "this vertex has zero/no weight" — feeding one of them a `dirty_verts`-
> trimmed dict where it expects the complete active layer will silently zero
> every vertex outside the trim. This exact bug (color-wipe / "untouched
> vertex goes black") was hit and fixed **twice** in this session, both times
> from the same root cause. Any new code on this path must keep the "small
> diff for the Rust call" and "complete dict for everything downstream"
> objects structurally distinct (see `res_layer_diff`/`res_mask_diff` vs.
> `full_layer_int` in `apply_action()` — the naming is deliberate, not
> decorative).

Concrete places this contract applies:
- `flatten_to_mesh_edit()`'s `active_layer_override` must be the complete
  active layer, never trimmed — only the post-composite BMesh *write* loop
  and `write_layer_to_temp_vgs_bm()`'s sync loops are safe to restrict.
- `write_active_layer_from_calc()`'s `layer_int` argument must always be
  complete; it does its own internal trimming for the parts that are safe to
  trim (the EDIT+temp-VG hot path's string conversion), while the Object-Mode
  `ss_layer_N` persistence fallthrough always needs and uses the full dict.
- The Rust-bound payload (`layer_int_for_rust`/`mask_dict_for_rust` in
  `apply_action()`) IS safe to trim to `dirty_verts`, because every
  `rust_*_logic` function's write set is exactly `selected`, and its only
  reads outside `selected` are neighbor lookups `dirty_verts` already
  guarantees are present (verified by reading `simple_ops_logic.rs`/
  `smooth_logic.rs` directly — don't assume this holds for a new Rust
  function without checking its actual read set the same way).

`dirty_verts` for smooth/sharpen must be **reused from the exact same
`neighbors` dict already being passed to the Rust call** — never independently
re-derived — or it can silently under-cover what Rust actually changed.

---

## FFI Marshaling Findings (COO rewrite, and why it under-delivered)

A Rust flat-array (COO) rewrite of the layer compositor's non-active-layer
FFI payload (`rust_composite_layers_mixed` in `rust_logic/src/layer_compositor.rs`,
gated by `hasattr(rust.module, "rust_composite_layers_mixed")` in
`core_subsystems/layer_compositor/codec.py`) was built to replace
`HashMap<usize, HashMap<String,f32>>` (string-keyed) with numeric COO arrays,
on the theory that per-element FFI marshaling would be cheaper.

**Measured result: the win was small.** Real profiling (`SSP_PROFILE_COMPOSITOR=1`)
showed `rust_call` time essentially unchanged (~4.1-4.4ms) even with a tiny
`dirty_verts` and only 2 visible layers. **Root cause: PyO3 always deep-copies
array/dict data element-by-element when crossing the FFI, regardless of
whether the Python-side object is the exact same cached instance as the
previous call.** Python-side memoization (`functools.lru_cache` on the decode
step) does not avoid this — the expensive part is the FFI crossing itself,
not the Python-side decode work, and that crossing happens unconditionally on
every `rust.call(...)`. If you're about to try another "make the payload
shape cheaper" rewrite here, know this ceiling exists first — the shape of
the data crossing the FFI matters less than *whether it needs to cross at
all*.

**A persistent Rust-side cache (state living inside the compiled `.so`,
keyed on `bpy.types.ID.session_uid` + layer index, to skip re-sending
unchanged non-active layers entirely) was designed but NOT implemented** —
the user stopped the work before implementation began. If resumed later, the
design (session_uid as the correct mesh-identity key instead of `id(mesh_data)`
which is unsafe due to CPython object-id reuse after GC; hash-verified
cache-miss must raise an error and force a resend, never silently produce
empty/wrong data; LRU-bounded to avoid unbounded session-long growth) is a
reasonable starting point, but its own honest self-assessment flagged real
uncertainty: the active layer's per-tick payload is untouched by this design
(so it only helps if a large, static non-active layer is truly the
bottleneck), and the new `Mutex` lock + `HashMap.clone()` per cache hit is
itself a new cost that could eat into the savings — this needs a cheap
diagnostic measurement (log COO array sizes per layer alongside existing
`_PROFILE_COMPOSITOR` timing) to confirm the bottleneck's actual location
before investing further engineering effort.

**A separate, real win that WAS confirmed and shipped**: `interface/utils/utils.py::_get_visible_influence_bones()`
was fully rescanning the mesh on every single gesture tick, because its
cache key included `ShaderManager.get_deform_generation()`, which the
gesture bumps on every completed write. Fixed with a
`_INFLUENCE_VISIBLE_DEBOUNCE_SECONDS` (`0.2s`) debounce: a stale-but-recent
cached result is returned without a full rescan if the last recompute was
within the debounce window, and the cache key is deliberately left
un-updated on a debounce-skip so the next call past the window still forces
one final, correct recompute. This is a good template for any other
per-tick-invalidated cache found on this hot path in the future — check
whether a UI/display-only cache (not the actual weight data) can tolerate a
similar bounded staleness window before assuming it needs a bigger structural
fix.

---

## Files Touched By This Body of Work (for quick orientation)

- `features/weight_apply/weight_apply_feature.py`, `logic.py`, `ops.py`, `ui.py` — the domain itself.
- `features/circle_tool_adjust/ops.py`, `keymap.py`; `features/bone_picker/ops.py`, `keymap.py` — displaced shortcuts, `_trigger_type` fix.
- `core/facade/write.py`, `core/ui_controller/pipeline.py`, `core/layer_storage/temp_vg_bridge.py` — `dirty_verts`/`active_layer_override`/`mask_override` threading (core/ access was explicitly user-authorized for this performance work; see `core/facade/README.md` for the current contract).
- `core_subsystems/layer_compositor/codec.py`, `core_subsystems/rust_weight_engine/flat_array_bridge.py`, `rust_logic/src/layer_compositor.rs`, `rust_logic/src/lib.rs` — the COO flat-array FFI path.
- `interface/utils/utils.py` — `_get_visible_influence_bones()` debounce.
