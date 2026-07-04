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

`execute()` reads the active layer via `core_facade.read_active_layer()` and writes
the result back via `core_facade.write_active_layer()`. In Edit Mode these route
through the `__ssp_*` BMesh temp Vertex Groups, not `ss_layer_N` directly — every
weight op therefore does two things on write: it updates the temp VGs (so Blender's
native Undo tracks the step), and it flattens the composite of all layers (including
the just-updated temp VG) onto the real deform Vertex Groups so the Armature Modifier
and viewport update immediately. The permanent write-back to `ss_layer_N` only happens
when the user presses Save Weight or exits Edit Mode — never on every brush/action
call. See `core/facade/README.md` ("Mode-Aware Layer Read/Write") and
`docs/bug-history/0016`, `0018`, `0019` for the underlying design.

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