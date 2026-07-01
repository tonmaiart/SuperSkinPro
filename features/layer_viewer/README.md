# LayerViewer Domain

## Domain Identity

- **Domain ID:** `layer_viewer`
- **Actions:** *(none — viewer-only domain)*
- **Tab:** `LAYER` (Object Mode context)
- **Priority:** First under the LAYER tab (`collapsible=False`)

## Architecture & Dataflow

```
LAYER Tab (Widget Preferences)
  └─ PrefsExtensionRegistry.get_by_tab('LAYER')[0]
       └─ prefs.draw_section_fn(layout)
            └─ ui.draw_layer_list(layout, context, rows=8)
                 └─ draw_list_with_sidebar(...)
                      └─ template_list("SUPERSKIN_UL_layer_list_view", ...)
                           └─ SUPERSKIN_OT_layer_select_by_item (row-click)
                                └─ LayerListAdapter.on_single_select()
                                     └─ CoreFacade(context).get_ctrl().switch_to_layer(index)
```

No DomainRegistry dispatching occurs — `LayerViewerDomain.execute()` is
never called. The DomainRegistry entry is structural only.

## File Manifest

| File | Responsibility |
|------|----------------|
| `__init__.py` | Package lifecycle — registers ui, then prefs |
| `layer_viewer_domain.py` | BaseDomain stub — satisfies DomainRegistry contract |
| `ui.py` | UIList, adapter, row-click operator, draw function |
| `prefs.py` | PrefsExtensionSpec registration under LAYER tab |
| `default_config.json` | Empty factory defaults (no persistent settings) |
| `README.md` | This document |

## Guardrails & Invariants

- **No persistent settings:** `populate_fn` and `serialize_into_fn` are no-ops.
- **collapsible=False:** The layer list renders without a collapsible header,
  matching its previous non-collapsible behaviour in the SKINNING tab.
- **Object Mode context:** The LAYER tab is intended for use in Object Mode.
  `draw_section_fn` guards against missing `ss_layers_meta` and shows a
  hint to enter Edit Mode when the layer system has not been initialized.
- **Undo:** Layer CRUD operators manage their own undo stacks via temp VGs;
  this viewer injects no parallel undo logic.
- **bl_idname stability:** `SUPERSKIN_OT_layer_select_by_item`,
  `SUPERSKIN_UL_layer_list_view`, and `SUPERSKIN_MT_layer_rename_overflow`
  are unchanged from their previous location in `ui/widget_tools.py`.
