# Clipboard Domain Specification

Global application singleton managing the cut, copy, and paste pipeline for skin weights and mask states between vertices, layers, and separate mesh targets.

## ⚙️ Domain Actions Matrix

| Action | Purpose |
|---|---|
| `copy` | Captures selected vertex attributes into memory. |
| `cut` | Snapshots selection, then clears source storage under an undo block. |
| `paste_add` | Merges clipboard data by adding values up to a ceiling of 1.0. |
| `paste_subtract` | Deducts clipboard data from target vertex arrays, flooring at 0.0. |
| `paste_replace` | Overwrites destination vertex storage arrays completely. |
| `select_affected` | Queries and highlights all vertices affected by the active channel. |

*Operators: `object.ssp_copy_weight`, `object.ssp_cut_weight`, `object.ssp_paste_weight_add`, `object.ssp_paste_weight_subtract`, `object.ssp_paste_weight_replace`.*

## 🗺️ Vertex-Count Resolution Matrix
At paste execution, `resolve_paste_targets_*()` in `core_subsystems/layer_compositor/data_operations.py` evaluates targets against the active selection:

| Clipboard Verts (clip) | Target Selected Verts | Mesh Context | Result Behavior |
|---|---|---|---|
| `1` | `N` | Cross-mesh OK | **Broadcast:** Pastes the single source vertex onto all targets. |
| `N` | `1` | Cross-mesh OK | **Blend:** Averages all clipboard inputs into one aggregate vertex slot. |
| `N` | `N` | Same Mesh ONLY | **Pair:** Zips matching array offsets sequentially 1:1. |
| `N` | `M` (Mismatch) | Any | ❌ **INVALID** -> Warning popup, cancels execution. |
| `N` | `N` | Cross-mesh | ❌ **INVALID** -> Warning popup, cancels execution. |

*Rule 0: An empty selection array on either Copy or Paste triggers a Whole-Mesh Fallback, capturing or applying values across all vertices.*

## 🔄 Cross-Tab Conversion Rules
Handles out-of-context data transfer gracefully behind the scenes:
- **WEIGHT Clipboard ➔ MASK Context:** Pivots through the active vertex group index. Extracts only the specific weight of the **Active Bone** and populates the target mask float dictionary.
- **MASK Clipboard ➔ WEIGHT Context:** Stamps the mask intensity float directly onto the **Active Bone** slot within the destination layer.

## 🚨 Rules for Agents & Guard Order
To minimize token consumption and avoid polluting the Blender undo stack with malformed steps, evaluate all validations and bone sets using `validate_bone_compatibility` up front before performing any mutation. If any verification fails, raise a `ValueError` to terminate the loop cleanly. Note: `undo_manager.push()`/`sync_checksum()` are no-op stubs under the native temp-vertex-group undo protocol (see project `CLAUDE.md`) — do not gate this logic on them.