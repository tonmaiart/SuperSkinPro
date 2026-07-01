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