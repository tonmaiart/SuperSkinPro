# 📁 Weight IO Domain (`data_io`)

This domain handles the serialization and deserialization of vertex weight maps to and from standardized external `.json` structures. It provides artists with the ability to archive, backup, or transfer layer weight data between different meshes or layer slots.

## 🏛️ Architecture & Dataflow
Like all extra domains, `data_io` communicates with the core system exclusively via `CoreFacade`. It utilizes Blender's native `ExportHelper` and `ImportHelper` to handle file paths synchronously from thin operator shells.

```text
[Blender UI Operator] ➔ context.window_manager["superskin_io_filepath"] ➔ run_domain("data_io") 
                      ➔ WeightIODomain.execute() ➔ WeightIOProcessor 
                      ➔ CoreFacade.write_layer_dict() ➔ CoreFacade.finish()
```

### File Manifest
- `logic.py`: WeightIOProcessor — JSON serialization/deserialization
- `ops.py`: Blender operators for export/import (ExportHelper/ImportHelper)
- `prefs.py`: PropertyGroup + PrefsExtensionRegistry registration
- `data_io_domain.py`: Domain execution bridge

## ⚠️ Guardrails & Invariants

- **Mode Requirement:** Import operator (`superskin.import_weight_json`) requires the mesh to be in **EDIT** mode with a valid active object. Export works in both EDIT and OBJECT modes.
- **Undo:** Import operations use native BMesh undo via temporary vertex groups (`__ssp_*`). No explicit `push_undo()` calls are needed or permitted.
- **File Format:** 
  - JSON with vertex indices as string keys
  - Bone names as string keys, weights as floating-point values
  - Example: `{"0": {"Bone.001": 0.75, "Bone.002": 0.25}}`
- **Precision:** Export precision defaults to 5 decimal places, configurable in Preferences (1-9 decimal places).
- **Clear Unmapped Bones:** When enabled, bones present in the current layer but absent in the imported JSON will be removed from the layer. Bones present in the imported JSON but absent from the current layer are added normally.
- **Error Handling:** Invalid JSON files or nonexistent file paths will show a toast notification and cancel the operation without modifying the layer.