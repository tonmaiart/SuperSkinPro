```markdown
# Mirror Domain Specification

Provides mirror capabilities for skin weights and mask data across a symmetrical axis using ngSkinTools-style search and replace name-matching pairs.

## ⚙️ Domain Actions Matrix

| Action | Operator ID | Purpose |
|---|---|---|
| `mirror` | `object.mirror_weights` | Mirrors weight and mask topologies across the chosen axis. |

*Note: Pair management operators (`superskin.add_mirror_sr` and `superskin.remove_mirror_sr`) manipulate the `SUPERSKIN_UL_mirror_sr` UIList descriptor.*

## 🧬 Core Logic Flow & FFI Bridges
1. **Planning Step (String-Based):** `generate_pairs` resolves symmetrical name pairs based on 3D bone centers and search/replace rules. This step operates strictly on bone name strings.
2. **Apply Step (Integer-ID CSR Bridge):** Converts matched strings to Integer IDs before invoking the Rust core. Mask mirroring utilizes `mask_to_flat()` to build dense contiguous flat buffers for zero-copy FFI execution via `rust_mirror_apply_mask_flat`.

## 🛠️ Configuration Spec (`default_config.json`)
```json
{
  "mirror_axis": "X",
  "direction": "POS_NEG",
  "both_data": true,
  "search_replace_pairs": [
    ["*.l", "*.r"],
    ["*.L", "*.R"],
    ["*_L", "*_R"],
    ["*_l", "*_r"]
  ]
}