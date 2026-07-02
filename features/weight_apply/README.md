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
  "smooth_affected_only": false
}
```

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