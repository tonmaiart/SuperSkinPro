# 📁 Weight IO Domain (`data_io`)

This domain handles serialization and deserialization of the **entire layer stack** (weights, masks, and per-layer metadata) to and from a standardized external `.json` file. It provides artists with the ability to archive, back up, or transfer a mesh's full layer stack.

## 🏛️ Architecture & Dataflow
`data_io` is a viewer-style extension with no dispatched actions (`actions = []`). Export/import are self-contained Blender operators in `ops.py` that talk to `CoreFacade` directly — `DataIOFeature.execute()` is a stub that always returns `{"status": "CANCELLED"}` and is never actually invoked from the UI.

```text
[Export JSON button] ➔ WM_OT_superskin_export_json.execute()
                     ➔ CoreFacade.get_meta_list() / switch_to_layer() / get_active_layer_dict() / get_active_mask_dict()
                     ➔ json.dump() to disk

[Import JSON button] ➔ WM_OT_superskin_import_json.execute()  (EDIT mode only)
                     ➔ removes ALL existing layers, rebuilds each from the file
                     ➔ CoreFacade.write_layer_dict() / write_mask_dict() per layer ➔ CoreFacade.finish()
```

### File Manifest
- `data_io_feature.py`: `DataIOFeature(UnifiedFeatureExtension)` — `SSPrefWeightIO` PropertyGroup (`export_precision`, `clear_unmapped_bones`), UI layout (export/import buttons + settings box), JSON persistence hooks. No action dispatch is actually used.
- `ops.py`: `WM_OT_superskin_export_json` (`superskin.export_weight_json`) and `WM_OT_superskin_import_json` (`superskin.import_weight_json`) — self-contained `ExportHelper`/`ImportHelper` operators that own the full read/write pipeline.

## ⚠️ Guardrails & Invariants

- **Mode Requirement:** Import operator (`superskin.import_weight_json`) requires the mesh to be in **EDIT** mode with a valid active mesh object (`poll()` check). Export works with any active mesh object regardless of mode.
- **Import is destructive/wholesale:** Import does **not** merge into the current layer stack. It removes every existing layer (`ctrl.remove_layer()` per slot) and rebuilds the entire stack from the file's `layers` array. There is no partial/single-layer import path.
- **File Format:** JSON with a top-level `version`, `active_layer_index`, and a `layers` array. Each layer entry has `slot`, `name`, `visible`, `mask_default`, `locks`, `weights` (`{"<v_idx>": {"<bone_name>": weight}}`), and `mask` (`{"<v_idx>": mask_value}`).
- **Precision:** Export precision defaults to 5 decimal places, configurable in Preferences (1–9 decimal places). Zero-weight bone entries and zero-value mask entries are skipped during export.
- **Known limitation — locks are not restored:** `locks` is captured on export but the import path does not currently write it back onto the rebuilt layer (no-op placeholder in `ops.py`); imported layers always come back with default bone-lock state.
- **`clear_unmapped_bones` is currently unused:** The setting is drawn in the UI and persisted to `default_config.json`, but the import operator does not read it — it has no effect on import behavior today.
- **Undo:** Import/export use standard Blender operator undo (`bl_options = {'REGISTER', 'UNDO'}`); no explicit `push_undo()` calls are made or permitted.
- **Error Handling:** Invalid JSON files, missing `layers` key, or nonexistent file paths report an error and cancel the operation without modifying the layer stack.
