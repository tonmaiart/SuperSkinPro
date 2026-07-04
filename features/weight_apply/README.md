# Weight Apply Domain Specification

Core module managing weight and mask brush operations (Add, Scale, Smooth, Sharpen). All operations are processed via the native Rust Acceleration Core and are bound by the active layer's bone lock states.

## ⚙️ Domain Actions Matrix

| Action | Operator ID | Purpose |
|---|---|---|
| `add` | `object.mw_add_weight` | Adds weight/mask values based on brush intensity. |
| `scale` | `object.mw_scale_weight` | Multiplies existing weights on affected vertices. |
| `smooth` | `object.mw_smooth_weight` | Averages weights across neighboring vertices. |
| `sharpen` | `object.mw_sharpen_weight` | Enhances contrast by pulling weights toward the center vertex. |

## 🧬 Data Structures & FFI Pipelines
To eliminate overhead, data serialization crossing the FFI boundary uses flat buffers and strict integer-keyed mappings. String-to-Integer mapping is handled exclusively inside the core choke-points.
- **Layer Weights (In-Memory Integer Mapping):** `{ v_idx (int): { bone_id (int): weight (float) } }`
- **Mask Layout (In-Memory Flat Format):** `{ v_idx (int): mask_value (float) }`
- **Locks Constraints Map:** `{ bone_id (int): is_locked (bool) }`

## 🛠️ Configuration Spec (`default_config.json`)
```json
{
  "add_val": 0.61,
  "scale_val": 0.61,
  "smooth_val": 0.61,
  "sharpen_val": 0.61,
  "smooth_affected_only": false,
  "smooth_across_surface": false
}
```

## 🌐 Smooth Across Surface

`smooth_affected_only` and `smooth_across_surface` are independent toggles: the
former filters *which vertices* get touched, the latter changes *which
neighbors* count toward each vertex's average.

Plain smoothing averages over `core_facade.get_cached_mesh_neighbors()`
(1-ring adjacency), which ties the effective smoothing radius to hop count —
dense topology smooths slower per unit distance than sparse topology. When
`smooth_across_surface` is enabled, `logic.build_surface_neighbors()` walks the
1-ring adjacency graph via bounded BFS, accumulating edge length as an
approximate geodesic distance, and returns an expanded `{v_idx: [neighbor_idx,
...]}` map sized to a comparable real-world radius regardless of local
topology density. This map is passed to the exact same `rust_smooth_logic`
FFI call in place of the raw 1-ring neighbors — no Rust/core code is touched,
only the Python-side `neighbors` argument changes shape. Results are cached
per vertex per mesh identity (`_SURFACE_CACHE` in `logic.py`) since the map
depends only on topology/coordinates, not on weight data. The cache key
includes `radius_multiplier`/`max_hops` since Smooth and Sharpen request
different neighborhood sizes for the same mesh.

## 🔺 Sharpen Neighbor Widening

`sharpen` always feeds `build_surface_neighbors(..., radius_multiplier=
SHARPEN_RADIUS_MULTIPLIER)` (currently `2.0`) instead of the raw 1-ring
`get_cached_mesh_neighbors()`. Plain 1-ring adjacency is often only 4-6
vertices, so a single neighbor clamping to 0.0/1.0 in `rust_sharpen_logic`
dominates the contrast average, and repeated presses cascade into a
checkerboard-style divergence (isolated per-vertex spikes instead of a
cohesive ring/zone). Widening the neighborhood dilutes any single saturated
vertex's influence. This is unconditional (no checkbox) since the tight
1-ring average was the bug, not an alternate mode — the Rust formula in
`rust_sharpen_logic` itself is untouched.

## 🖱️ Gesture Shortcuts (`keymap.py` + `ops.py`)

| Shortcut | `action` property | Positive drag | Negative drag |
|---|---|---|---|
| Alt+LMB | `add_scale` | Add | Scale |
| Alt+RMB | `smooth_sharpen` | Smooth | Sharpen |

Both bind to one modal operator, `superskin.weight_gesture`
(`SUPERSKIN_OT_weight_gesture` in `ops.py`), parametrized by the `action`
string property set per-keymap-item in `keymap.py`. Interaction contract:

- **Hold-only — there is no plain-click apply.** A click that never crosses
  the drag threshold does nothing (no write, no undo step). Only a real
  hold + drag registers.
- **Hold + drag**: horizontal mouse movement live-previews a single signed
  value in `[-1.0, 1.0]` starting at `0.0`. The sign picks which of the two
  real actions runs (`_COMBINED_RESOLVERS` in `ops.py`); the magnitude
  becomes that action's intensity:
  - `add_scale`: `[0, 1]` → `add(v)`; `[-1, 0]` → `scale(1.0 + v)` (dragging
    left from 0 ramps Scale's intensity down from `1.0`, i.e. no change, to
    `0.0`, i.e. fully zeroed, at `-1.0`).
  - `smooth_sharpen`: `[0, 1]` → `smooth(v)`; `[-1, 0]` → `sharpen(-v)`
    (dragging left from 0 ramps Sharpen's intensity up from `0.0` to `1.0`
    at `-1.0`).
  - `0.0` is the neutral start for both directions, so click-without-drag
    naturally corresponds to "nothing happens" — consistent with there being
    no plain-click apply at all.
  Releasing commits the final resolved value. Every `MOUSEMOVE` warps the
  cursor back to the press position (infinite-drag, same trick as
  `CircleToolAdjust`), so each event's `delta` is only the movement since
  the last warp and must be *added* to the running value, never used as an
  absolute offset from the start position (that was a past bug: recomputing
  from the raw offset capped the reachable value at whatever a single
  event's movement could produce, ~0.03-0.04).
- **No mid-gesture cancel by design**: there is no ESC/cancel branch. Once
  a drag starts, release always commits; reverting is Ctrl+Z only
  (Blender's native undo), never an in-tool cancel action.
- `add_scale` requires an active bone at invoke (both Add and Scale need
  one) and cancels immediately without one. `smooth_sharpen` doesn't gate at
  invoke — Smooth has no active-bone requirement, and if the drag crosses
  negative into Sharpen with no active bone, that side's own per-call check
  inside `apply_action()` just no-ops for that frame.

To make this preview possible without compounding on every mouse-move,
`WeightApplyFeature.snapshot_context()` reads the layer/mask/selection/locks
baseline **once** at gesture invoke, and `apply_action()` recomputes fresh
from that fixed snapshot at whatever intensity the drag currently reports
(never mutating the snapshot). `execute()` (the single-shot panel-button
path) is just `snapshot_context()` + one `apply_action()` call using the
configured intensity — both paths share the same compute/write logic.

Alt+LMB and Alt+RMB previously belonged to `circle_tool_adjust` and
`bone_picker` respectively. `circle_tool_adjust`'s shortcut moved to
Alt+Shift+RMB (via a brief stop at Alt+Ctrl+LMB); `bone_picker`'s
overlay-size shortcut moved to Alt+Shift+MMB. See those domains'
README/keymap.py for notes.

## 🔄 Edit-Mode Write Workflow

`execute()` / `apply_action()` read the snapshot baseline via `snapshot_context()`
(`core_facade.read_active_layer()` et al., taken once per gesture/click) and write
the result back via one of three paths depending on context, all in `apply_action()`:

- **Mask mode**: `ctrl._write_active_layer_string(full_layer_int, id_to_bone, full_mask, is_mask_mode=True, dirty_verts=dirty_verts)` + `core_facade.finish(color_only=True, dirty_verts=dirty_verts)`.
- **EDIT mode (non-mask, the gesture's hot path)**: `core_facade.write_active_layer_from_calc(full_layer_int, id_to_bone, dirty_verts=dirty_verts, mask_override=mask_dict)` — takes Rust's int-keyed output directly (skips the int→string→int round-trip `write_active_layer()` does) and already flattens + redraws inline, so no separate `finish()` call.
- **Object mode**: `core_facade.write_active_layer(res_layer_str, color_only=True, dirty_verts=dirty_verts)` — Object-Mode's `write_active_layer_from_calc()` branch only persists to storage without flattening, so this path keeps the slower string round-trip (which calls `finish()` internally).

In Edit Mode these route through the `__ssp_*` BMesh temp Vertex Groups, not
`ss_layer_N` directly — every weight op therefore does two things on write: it
updates the temp VGs (so Blender's native Undo tracks the step), and it flattens the
composite of all layers (including the just-updated temp VG) onto the real deform
Vertex Groups so the Armature Modifier and viewport update immediately. The permanent
write-back to `ss_layer_N` only happens when the user presses Save Weight or exits
Edit Mode — never on every brush/action call. See `core/facade/README.md`
("Mode-Aware Layer Read/Write") and `docs/bug-history/0016`, `0018`, `0019` for the
underlying design.

## ⚡ Gesture Performance: `dirty_verts` and the Rust FFI Path

The modal gesture (`SUPERSKIN_OT_weight_gesture`) applies on a `TIMER` event
throttled to `_GESTURE_APPLY_INTERVAL` (currently `1.0/60.0`) in `ops.py`, not
on every raw `MOUSEMOVE` — `MOUSEMOVE` only accumulates `self._drag_value`
(cheap arithmetic); the timer is what actually calls `_apply()`.

Each `apply_action()` call computes `dirty_verts` — always a superset of
`selected`, widened for `smooth`/`sharpen` by the exact same `neighbors` dict
already being passed to the Rust call (never a separately re-derived
approximation, so it cannot under-cover what Rust actually changes).
`dirty_verts` is threaded into every write call above and further down into
`core/facade/write.py`, `core/ui_controller/pipeline.py::flatten_to_mesh_edit()`,
and `core/layer_storage/temp_vg_bridge.py`, restricting their BMesh scans and
compositor recomputation to only vertices this tick could have touched
instead of the whole mesh. Only the vertex-**iteration** is restricted this
way — the compositor's active-layer input itself (via `active_layer_override`)
must always be the complete, current layer, never a `dirty_verts`-trimmed
one, or vertices outside `dirty_verts` would look like they have zero weight
and get silently zeroed (this exact bug was hit and fixed once already).

The Rust-bound payload for `apply_add`/`apply_scale`/`apply_smooth`/
`apply_sharpen` (`layer_int_for_rust`/`mask_dict_for_rust`) is trimmed to
`dirty_verts` — safe because every `rust_*_logic` function's write set is
exactly `selected`, and reads outside `selected` are only neighbor lookups
`dirty_verts` already guarantees are present. Rust's return is deliberately
named `res_layer_diff`/`res_mask_diff` (never `res_layer`/`res_mask`) and
merged into a separately-built `full_layer_int`/`full_mask` before any
downstream write — passing the small diff anywhere a complete dict is
expected reproduces the "untouched vertex's color goes black" bug.

The layer compositor itself (`core_subsystems/layer_compositor/codec.py`,
`rust_logic/src/layer_compositor.rs`) has a flat-array (COO) FFI path
(`rust_composite_layers_mixed`) for non-active visible layers, used only
when `hasattr(rust.module, "rust_composite_layers_mixed")` — older compiled
`rust_logic.so` binaries transparently keep using the original dict-based
`rust_composite_layers` until rebuilt. Real profiling showed this rewrite's
win is small in practice (PyO3 still deep-copies array data on every call
regardless of Python-side caching), since the true remaining cost is
re-marshaling large, unchanged non-active layers across the FFI every tick —
see `core_subsystems/layer_compositor/codec.py` for the current state of
this investigation before assuming this path is "fast."

A related, previously-hidden cost: `interface/utils/utils.py::_get_visible_influence_bones()`
(used by the Deform Bone Viewer panel) used to fully rescan the mesh on
every single gesture tick, because its cache key included
`ShaderManager.get_deform_generation()`, bumped on every completed weight
write. It now has a `_INFLUENCE_VISIBLE_DEBOUNCE_SECONDS` (`0.2s`) debounce
window so a continuous gesture doesn't force a full mesh rescan every tick —
see that file for details; not specific to this domain, but directly
triggered by this domain's write-every-tick behavior.

`layer_int` is built only over `layer_str.items()` (vertices with existing weight),
not the full mesh vertex range — the Rust smoothing/sharpening functions already
default missing vertices/bones to `0.0`, so padding the dict with empty entries for
every mesh vertex is a no-op for the math and only wastes a full `O(num_verts)` pass
on every Add/Scale/Smooth/Sharpen call.

`write_active_layer()` never touches the active layer's mask — it's the weight-only
counterpart to `write_mask_dict()`. See `docs/bug-history/0020` for a bug where the
core write path (`core/facade/write.py`) passed an empty mask dict instead of `None`
into the Edit-Mode temp-VG writer, which silently wiped the layer's mask on every
call to `write_active_layer()`.