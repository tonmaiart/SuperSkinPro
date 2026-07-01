### `features/auto_block_weight/README.md`

```markdown
# Auto Block Weight Domain Specification

Assigns a solid 100% weight influence to selected vertices by evaluating the closest unlocked bone using a specialized Loop-Axis Aligned algorithm.

## ⚙️ Domain Actions Matrix

| Action | Operator ID | Purpose |
|---|---|---|
| `auto` | `mesh.auto_assign_closest_unlocked_bone` | Precomputes mesh metrics and snaps vertices to the closest bone. |

## 🧬 Hybrid Architecture Pipeline
Due to FFI bottlenecks regarding complex raycasting, this feature implements a strict hybrid pipeline:
1. **Python Pre-compute Phase (Raycast Gate):** Extracts the BVH Tree from `ctrl.storage.build_bvh_tree()` and performs edge-raycasting inside Python to generate a sparse `hit_count_map`.
2. **Rust Scoring Phase:** The raw hit count map and world coordinates are dispatched via `rust_auto_logic`, where Rust processes the spatial math and returns a strict String name assignment map.

## 🚨 Rules for Agents
1. **Mask Context Guard:** Check `ctrl._is_mask_context()`. If the user is inside a mask-painting layout, immediately cancel the transaction and return `CANCELLED`. Auto Block is restricted to bone weight painting only.
2. **Normalisation Cycle:** After parsing the assignments, call `CoreFacade.normalize_weights()` to re-balance the remaining vertex weight budgets against locked bones.