# LayerViewer Domain

## Domain Identity

- **Domain ID:** `layer_viewer`
- **Actions:** *(none — viewer-only domain)*
- **Tab:** `LAYER`
- **Priority:** `0` — first under the LAYER tab. `collapsible = True`, `expanded_by_default = True`.

## Architecture & Dataflow

```
LAYER Tab (widget_preferences.py)
  └─ UnifiedRegistry.get_by_tab('LAYER')  → LayerViewerFeature (priority 0, rendered first)
       └─ LayerViewerFeature.draw_section(layout, context)
            └─ ui.draw_layer_list(box, context, rows=8)
                 └─ draw_list_with_sidebar(...)
                      └─ template_list("SUPERSKIN_UL_layer_list_view", ...)
                           └─ SUPERSKIN_OT_layer_select_by_item (row-click)
                                └─ LayerListAdapter.on_single_select()
                                     └─ CoreFacade(context).get_ctrl().switch_to_layer(index)
```

No action dispatching occurs — `LayerViewerFeature.execute()` always returns `{"status": "CANCELLED"}` and is never actually called from the UI; the registry entry exists purely so the domain renders in its tab.

## File Manifest

| File | Responsibility |
|------|----------------|
| `__init__.py` | Package lifecycle — bottom-up micro-reload, registers `ops` then `layer_viewer_feature` |
| `layer_viewer_feature.py` | `LayerViewerFeature(UnifiedFeatureExtension)` — no-op action dispatch, UI layout (renders `ui.draw_layer_list` plus an "Enter Layer Edit" button), no persistent settings |
| `ui.py` | `LayerListAdapter`, `SUPERSKIN_OT_layer_select_by_item`, `SUPERSKIN_UL_layer_list_view`, `SUPERSKIN_MT_layer_rename_overflow`, `draw_layer_list()` |
| `ops.py` | Layer CRUD operators: `SUPERSKIN_OT_layer_toggle_visible_by_item`, `SUPERSKIN_OT_layer_add`, `SUPERSKIN_OT_layer_remove`, `SUPERSKIN_OT_layer_move`, `SUPERSKIN_OT_layer_duplicate`, `SUPERSKIN_OT_layer_merge_selected`, `SUPERSKIN_OT_layer_rename_active` |
| `default_config.json` | Empty factory defaults (no persistent settings) |
| `README.md` | This document |

## Guardrails & Invariants

- **No persistent settings:** `populate()` and `serialize_into()` are no-ops.
- **`collapsible = True` / `expanded_by_default = True`:** The layer list still renders inside the standard collapsible-box wrapper (unlike the primary SKINNING-tab viewer, `deform_bone_viewer`), but starts expanded by default.
- **Object Mode context:** `draw_section()` guards against a missing/non-mesh active object and against `ss_layers_meta` not yet existing on the mesh, showing a hint to enter Edit Mode when the layer system has not been initialized.
- **Cross-domain button reference:** The "Enter Layer Edit" button invokes `superskin.enter_layer_edit`, which is defined in `features/controller/ops_scene_modes.py`. This references the operator by `bl_idname` string only (via `layout.operator(...)`) — it is not a Python import, so it does not violate the Zero Cross-Imports rule between feature packages.
- **Undo:** Layer CRUD operators manage their own undo via standard Blender operator undo (`bl_options` on each `ops.py` class); this viewer injects no parallel undo logic.
- **bl_idname stability:** `SUPERSKIN_OT_layer_select_by_item`, `SUPERSKIN_UL_layer_list_view`, and `SUPERSKIN_MT_layer_rename_overflow` are unchanged from their previous location in `ui/widget_tools.py`.
