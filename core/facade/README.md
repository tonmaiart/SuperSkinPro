# 🏛️ CoreFacade API Specification

This document is the sole authoritative interface contract between SuperSkinPro Core and Extra Domains. Feature Agents working on `features/` MUST rely exclusively on this specification and are strictly prohibited from inspecting the implementation files inside `core/`.

---

## Architecture

The current architecture is `Blender Operator → CoreFacade → FeatureDomain`. `UIController` is a **private implementation detail** of `core/` — it is never imported or called outside of the `core/` package.

**Rules for feature domains:**
- Never import `UIController` directly. Use `CoreFacade` exclusively.
- `get_ctrl()` is an escape hatch for operations not yet promoted to an explicit facade method. Every call to it is a marker for a future facade addition. Prefer the explicit methods listed here.
- Any direct `UIController` import in `features/`, `operators/`, or `shared/` is an architecture violation.

---

## 🔍 Read Operations

### `get_active_layer_dict() -> dict`
- **Description:** Retrieves the weight data of the currently active layer.
- **Returns:** `{ v_idx (int): { bone_name (str): weight (float) } }`

### `get_active_mask_dict() -> dict`
- **Description:** Retrieves the mask/coverage data of the currently active layer.
- **Returns:** `{ v_idx (int): mask_value (float) }`

### `get_active_layer_index() -> int`
- **Description:** Returns the integer slot index of the active layer.

### `get_meta_list() -> list`
- **Description:** Reads the raw global layer metadata list (display order stack from `ss_layers_meta`).

### `get_selected_verts() -> list[int]`
- **Description:** Returns a list of vertex indices currently selected (auto-detects Edit/Object mode contexts).

### `get_active_vg_id() -> int | None`
- **Description:** Returns the active bone index. Supports real vertex group indices and synthetic IDs assigned to orphan bones. Returns `None` if unset.

### `get_active_vg_name() -> str`
- **Description:** Returns the name string of the active bone/vertex group. Returns `""` if none active.

### `get_vertex_groups() -> bpy_collection`
- **Description:** Direct passthrough to the active object's native `vertex_groups`.

### `get_obj() -> bpy.types.Object`
- **Description:** Returns the active Blender Object wrapped by the controller.

### `get_mesh() -> bpy.types.Mesh`
- **Description:** Returns the active Blender Mesh datablock wrapped by the controller.

### `is_mask_context() -> bool`
- **Description:** Returns `True` if the UI is currently in a mask-painting context (`superskin_is_mask_mode` or `superskin_skin_sub_tabs` is enabled).

### `get_local_mapping() -> tuple[dict[str, int], dict[int, str]]`
- **Description:** Returns two-way fast-lookup tables for real vertex groups: `(bone_to_id, id_to_bone)`.

### `get_bone_locks() -> dict[str, bool]`
- **Description:** Returns a dictionary mapping bone names to their lock status on the active layer.

### `get_vertex_coordinates() -> list[tuple[float, float, float]]`
- **Description:** Returns local-space coordinates `[(x, y, z), ...]` for every vertex in the mesh.

### `get_num_verts() -> int`
- **Description:** Quick accessor for total vertex count in the active mesh.

---

## 🔄 Mode-Aware Layer Read/Write

These methods route reads and writes through the correct data store for the current mode. **Use these instead of `get_active_layer_dict()` / `write_layer_dict()` whenever weights may be modified in Edit Mode.**

After the `0016` undo redesign, the active layer's source of truth in Edit Mode is the `__ssp_*` BMesh temp VGs, not `ss_layer_N`. Calling the plain read/write methods in Edit Mode silently accesses the wrong store — the root cause of bugs `0018` and `0019`.

### `read_active_layer() -> dict[int, dict[str, float]]`
- **Description:** Reads the active layer from the correct source for the current mode. Edit Mode: `__ssp_*` BMesh temp VGs. Object Mode: `ss_layer_N`.
- **Returns:** `{ v_idx (int): { bone_name (str): weight (float) } }`
- **Side effect:** Caches the unified bone mapping on the instance for a paired `write_active_layer()` call (avoids a second VG scan).

### `write_active_layer(layer_str: dict, *, color_only: bool = True)`
- **Description:** Writes a string-keyed layer dict to the correct target for the current mode, then calls `finish()`. Edit Mode: `__ssp_*` BMesh temp VGs. Object Mode: `ss_layer_N`. Also re-merges orphan entries and prunes zero-weight bones.
- **Input:** `{ v_idx (int): { bone_name (str): weight (float) } }`
- **Requires:** `read_active_layer()` should have been called first on this instance so the bone mapping cache is populated.

### `get_unified_mapping() -> tuple[dict[str, int], dict[int, str]]`
- **Description:** Returns `(bone_to_id, id_to_bone)` including synthetic IDs for orphan bones. Reuses the mapping cached by `read_active_layer()` if already called on this instance.
- **Usage:** Required by Rust domains that convert the string-keyed result of `read_active_layer()` to int-keyed data for FFI calls.

### `get_locks_by_id() -> dict[int, bool]`
- **Description:** Returns bone locks keyed by integer VG index (unified mapping). Use instead of `get_bone_locks()` when passing lock data to Rust functions that require int keys.

### `get_cached_mesh_neighbors() -> dict[int, list[int]]`
- **Description:** Returns the vertex-neighbor topology map in FFI-compatible form. Cached per mesh identity. Used by Rust smooth/sharpen operations.

---

## ✍️ Write Operations

### `write_layer_dict(layer_dict: dict)`
- **Description:** Commits a nested weight dictionary back to the active layer slot.
- **Input Format:** `{ v_idx (int): { bone_name (str): weight (float) } }`

### `write_mask_dict(mask_dict: dict)`
- **Description:** Commits a mask dictionary back to the active layer mask slot.
- **Input Format:** `{ v_idx (int): mask_value (float) }`

### `finish(*, color_only: bool = False)`
- **Description:** Macro call that reflattens storage layers to mesh vertex groups, updates tags, bumps deform generation, and schedules a visualizer redraw.
- **Parameters:** Set `color_only=True` for performance wins during rapid brush strokes when topology is untouched.

### `finish_color_only()`
- **Description:** Shorthand convenience wrapper for `finish(color_only=True)`.

### `write_active_layer_from_calc(layer_int: dict, id_to_bone: dict)`
- **Description:** Writes an integer-keyed layer dict (the direct output of a Rust computation) to the correct target for the current mode. Converts int-keyed data to string format via `data_bridge`, prunes zero bones, then routes through BMesh temp VGs in EDIT mode or `ss_layer_N` outside it.
- **Input Format:** `layer_int: { v_idx (int): { vg_index (int): weight (float) } }`, `id_to_bone: { vg_index (int): bone_name (str) }`
- **Notes:** Does NOT call `finish()`. The caller is responsible for calling `finish()` or `finish_color_only()` after all writes are complete. Handles weight writes only — does not process mask dicts or orphan re-merging.
- **Usage:** Preferred for Rust-backed domains (smooth, sharpen, auto-block) where data is already in int-keyed FFI format, eliminating the redundant string→int→string round-trip of `write_active_layer()`.

---

## 🎨 Shader / Viewport Visualizer Controls

### `invalidate_color_only()`
- **Description:** Flushes only the GPU color vertex buffers. Rebuilds vertex colors on the next draw call without heavy topology reconstruction.
- **Usage:** Ideal for bone hover, bone row selection, or active layer tab navigation changes.

### `invalidate_and_redraw()`
- **Description:** Full system cache flush. Erases and reconstructs wireframe lines, selection points, and color batches. Triggered automatically on global undos.

### `show_toast(text: str, duration: float = 1.0)`
- **Description:** Displays a short-lived, self-dismissing notification text centered in the 3D Viewport HUD.

---

## 🛠️ Utility & Convenience Methods

### `add_vg_selected(obj, name: str) -> bool`
- **Description:** Adds a bone name to the comma-separated global selection pool (`obj.superskin_storage.selected_names`).

### `remove_vg_selected(obj, name: str) -> bool`
- **Description:** Removes a bone name from the comma-separated global selection pool.

### `normalize_weights(layer_dict: dict, bone_locks: dict[str, bool], active_vg_name: str, is_mask: bool) -> dict`
- **Description:** Normalizes weights in a layer dict so that the sum of all unlocked bone weights at each vertex equals `1.0`. Locked bones are excluded from normalization. Pass `is_mask=True` to normalize a flat mask dict instead.
- **Returns:** A new normalized dict in the same format as the input.
- **Notes:** Implementation lives in `core_subsystems/weight_ops.py`.

### `switch_to_layer(index: int) -> None`
- **Description:** Switches the active layer to the given slot index, performing any necessary mode transitions (Edit Mode temp-VG bake/restore).

### `get_ctrl()`
- **Description:** **Escape Hatch.** Returns the internal controller instance.
- **Guideline:** Reserved for operations not yet promoted to an explicit CoreFacade method (e.g., `_gather_auto_bone_data`, visualizer mode toggles). Every `get_ctrl()` call in a feature domain is a marker for a future facade method addition. Use the explicit methods above for all layer read/write.