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
- **⚠️ NOT mode-aware.** Reads `ss_layer_N` directly — in Edit Mode with `__ssp_*` temp VGs present this is the Edit-Mode-entry snapshot, not the live BMesh state. Use `read_active_layer()` for any code path reachable in Edit Mode. See `docs/bug-history/0019`.

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
- **Description:** Returns `True` if the UI is currently in a mask-painting context (`superskin_is_mask_mode` is enabled). This flag is a derived side effect, written by `apply_active_bone()` on every call from `obj.superskin_storage.active_is_mask` — the Deform Bones list's Mask virtual row is the single source of truth; do not toggle `superskin_is_mask_mode` directly from feature code.

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

**Apply-Weight in Edit Mode always splits into two sub-steps, counted as a single undo step:**
1. **Update Temp VG** — the new weights are written into the `__ssp_*` BMesh deform layer. This is what Blender's native BMesh undo/redo actually tracks.
2. **Flatten to Real VG** — all visible layers (including the just-updated temp VG) are composited and written into the real deformation Vertex Groups, so the Armature Modifier recalculates the viewport deform immediately.

Both sub-steps happen inside the same Python call (`write_active_layer()` performs step 1, then calls `finish()` which performs step 2), so they land inside a single Blender operator execution and are therefore one atomic undo/redo step from the user's perspective — never two separate history entries.

`ss_layer_N` (the permanent, Object-Mode storage) is **not** touched by either sub-step. It is only written on a deliberate Save Weight action or on exiting Edit Mode (the bake path in `_exit_edit_mode`). Until then, all in-progress Edit Mode weight changes exist only in the `__ssp_*` temp VGs.

### `read_active_layer() -> dict[int, dict[str, float]]`
- **Description:** Reads the active layer from the correct source for the current mode. Edit Mode: `__ssp_*` BMesh temp VGs. Object Mode: `ss_layer_N`.
- **Returns:** `{ v_idx (int): { bone_name (str): weight (float) } }`
- **Side effect:** Caches the unified bone mapping on the instance for a paired `write_active_layer()` call (avoids a second VG scan).

### `write_active_layer(layer_str: dict, *, color_only: bool = True)`
- **Description:** Writes a string-keyed layer dict to the correct target for the current mode, then calls `finish()`. Edit Mode: writes to `__ssp_*` BMesh temp VGs (Update Temp VG), then `finish()` flattens all visible layers onto the real deform VGs (Flatten to Real VG) — see the two-sub-step note above. Object Mode: writes straight to `ss_layer_N`. Also re-merges orphan entries and prunes zero-weight bones.
- **Input:** `{ v_idx (int): { bone_name (str): weight (float) } }`
- **Requires:** `read_active_layer()` should have been called first on this instance so the bone mapping cache is populated.
- **Mask note:** This method writes weight data only. It calls the internal write path with no mask payload (`None`) — it must never be passed an empty dict `{}` in place of "no mask data," since the underlying Edit-Mode writer treats `{}` as "the mask is now empty everywhere" and clears it. See `docs/bug-history/0020`.

### `mutate_active_layer(*, color_only: bool = True) -> contextmanager`
- **Description:** Read-modify-write transaction for the active layer's weight data. `with facade.mutate_active_layer() as layer_data:` yields the dict from `read_active_layer()` for in-place mutation; on a clean exit it commits via `write_active_layer()` (mode-aware write + `finish()`). On an exception inside the block, nothing is written.
- **Usage:** Preferred over manually pairing `read_active_layer()` + `write_active_layer()` — makes the read-before-write ordering structurally guaranteed instead of relying on the caller to remember it. It is a thin composition of those two methods, not separate logic, so it never drifts out of sync with orphan/mask handling changes made to either.
- **⚠️ Must mutate `layer_data` in place** (`layer_data[v_idx][bone] = w`), never rebind the local name to a new dict (`layer_data = some_new_dict`). The generator holds the object reference from the original `yield`; rebinding the caller's local only changes what the caller's own code sees, not what gets committed on exit — the write would silently use the pre-mutation state. Code that computes a wholesale replacement dict (e.g. via `normalize_weights()`, which returns a new dict rather than mutating its argument) should call `read_active_layer()` / `write_active_layer()` directly instead of this wrapper.
- **Example:**
  ```python
  with facade.mutate_active_layer() as layer_data:
      for v_idx in facade.get_selected_verts():
          if v_idx in layer_data:
              for bone in layer_data[v_idx]:
                  layer_data[v_idx][bone] *= 1.1
  ```

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
- **⚠️ NOT mode-aware.** Writes `ss_layer_N` directly — in Edit Mode with `__ssp_*` temp VGs present this write is invisible to the live BMesh state and gets overwritten on Exit Edit Mode / layer switch. Use `write_active_layer()` or `mutate_active_layer()` for any code path reachable in Edit Mode. See `docs/bug-history/0019`. A debug-log warning fires automatically (category `core_pipeline`) if this is called while in Edit Mode with temp VGs present.

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

### `normalize_weights(layer_dict: dict, vertex_index: int, active_vg_name: str) -> dict`
- **Description:** Normalizes weights in a layer dict so that the sum of all unlocked bone weights at the given vertex equals `1.0`. Locked bones are excluded from normalization.
- **Returns:** A new normalized dict in the same format as the input.
- **Notes:** Delegates to `core_subsystems/context_selection_service/`'s `ContextSelectionService.normalize_weights`.

### `switch_to_layer(index: int) -> None`
- **Description:** Switches the active layer to the given slot index, performing any necessary mode transitions (Edit Mode temp-VG bake/restore).

### `get_ctrl()`
- **Description:** **Escape Hatch.** Returns the internal controller instance.
- **Guideline:** Reserved for operations not yet promoted to an explicit CoreFacade method (e.g., `_gather_auto_bone_data`, visualizer mode toggles). Every `get_ctrl()` call in a feature domain is a marker for a future facade method addition. Use the explicit methods above for all layer read/write.