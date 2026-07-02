# DeformBoneViewer Domain

## Domain Identity

- **Domain ID:** `deform_bone_viewer`
- **Actions:** *(none — viewer-only domain)*
- **Tab:** `SKINNING`
- **Priority:** `0` — first under the SKINNING tab. `collapsible = True`, `expanded_by_default = True`.

## Architecture & Dataflow

```
SKINNING Tab (widget_preferences.py)
  └─ UnifiedRegistry.get_by_tab('SKINNING')  → DeformBoneViewerFeature (priority 0, rendered first)
       └─ DeformBoneViewerFeature.draw_section(layout, context)
            └─ ui.draw_influence_list_system(box, context, rows=8)
                 └─ draw_list_with_sidebar(...)
                      └─ template_list("MESH_UL_influence_list_view", ...)
                           └─ SUPERSKIN_OT_select_vertex_group_row (row-click)
                                └─ BoneListAdapter.on_single_select()
                                     └─ CoreFacade(context).get_ctrl()
                                          ├─ ctrl.set_selected_bones(...)
                                          ├─ ctrl.set_active_bone_name(...)
                                          └─ ctrl.apply_active_bone()
```

No action dispatching occurs — `DeformBoneViewerFeature.execute()` always
returns `{"status": "CANCELLED"}` and is never actually called. The registry
entry exists purely so the domain renders in its tab.

## File Manifest

| File | Responsibility |
|------|----------------|
| `__init__.py` | Package lifecycle — bottom-up micro-reload, registers `ui`, `ops`, then `deform_bone_viewer_feature` |
| `deform_bone_viewer_feature.py` | `DeformBoneViewerFeature(UnifiedFeatureExtension)` — no-op action dispatch, UI layout (renders `ui.draw_influence_list_system` plus a "Save Weights & Exit" button), no persistent settings |
| `ui.py` | `BoneListAdapter`, `SUPERSKIN_OT_select_vertex_group_row`, `MESH_UL_influence_list_view`, `SUPERSKIN_MT_bone_extra_overflow`, `draw_influence_list_system()` |
| `ops.py` | `SUPERSKIN_OT_toggle_vg_lock`, `SUPERSKIN_OT_select_all_vgs`, `OBJECT_OT_mw_select_affect_vertices`, `MESH_OT_show_affect_bone`, `OBJECT_OT_mw_popup_affect_influences`, `OBJECT_OT_mw_select_specific_vertex_group`, `MT_mw_popup_affect_influences_menu`, `SUPERSKIN_OT_save_weight_and_exit` |
| `default_config.json` | Empty factory defaults (no persistent settings) |
| `README.md` | This document |

## Guardrails & Invariants

- **No persistent settings:** `populate()` and `serialize_into()` are no-ops.
- **Edit Mode context:** The SKINNING tab is intended for use in Edit Mode. `draw_section()` guards against a missing or non-mesh active object.
- **Orphan rows:** `MESH_UL_influence_list_view` routes orphan rows (whose `is_orphan` flag is True) to `superskin.select_orphan_bone_row` instead of the standard `superskin.select_vertex_group_row`. That operator is defined in `core/bone_identity/ops.py`, not in this package — it must remain registered there.
- **Adapter registry:** `BoneListAdapter` is registered under key `'BONES'` in `interface/template_ui/select_ops._adapter_registry` at `ui.register()` time.
- **bl_idname stability:** `SUPERSKIN_OT_select_vertex_group_row`,
  `MESH_UL_influence_list_view`, and `SUPERSKIN_MT_bone_extra_overflow`
  are unchanged from their previous location in `ui/widget_deform_bones.py`.
