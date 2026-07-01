# DeformBoneViewer Domain

## Domain Identity

- **Domain ID:** `deform_bone_viewer`
- **Actions:** *(none — viewer-only domain)*
- **Tab:** `SKINNING` (Edit Mode context)
- **Priority:** First under the SKINNING tab (`collapsible=False`)

## Architecture & Dataflow

```
SKINNING Tab (Widget Preferences)
  └─ PrefsExtensionRegistry.get_by_tab('SKINNING')[0]
       └─ prefs.draw_section_fn(layout)
            └─ ui.draw_influence_list_system(layout, context, rows=8)
                 └─ draw_list_with_sidebar(...)
                      └─ template_list("MESH_UL_influence_list_view", ...)
                           └─ SUPERSKIN_OT_select_vertex_group_row (row-click)
                                └─ BoneListAdapter.on_single_select()
                                     └─ CoreFacade(context).get_ctrl()
                                          ├─ ctrl.set_selected_bones(...)
                                          ├─ ctrl.set_active_bone_name(...)
                                          └─ ctrl.apply_active_bone()
```

No DomainRegistry dispatching occurs — `DeformBoneViewerDomain.execute()` is
never called. The DomainRegistry entry is structural only.

## File Manifest

| File | Responsibility |
|------|----------------|
| `__init__.py` | Package lifecycle — registers ui, then prefs |
| `deform_bone_viewer_domain.py` | BaseDomain stub — satisfies DomainRegistry contract |
| `ui.py` | UIList, adapter, row-click operator, draw function |
| `prefs.py` | PrefsExtensionSpec registration under SKINNING tab |
| `default_config.json` | Empty factory defaults (no persistent settings) |
| `README.md` | This document |

## Guardrails & Invariants

- **No persistent settings:** `populate_fn` and `serialize_into_fn` are no-ops.
- **collapsible=False:** The bone list renders without a collapsible header,
  matching its previous non-collapsible behaviour.
- **Edit Mode context:** The SKINNING tab is intended for use in Edit Mode.
  `draw_section_fn` guards against a missing active mesh object.
- **Orphan rows:** `MESH_UL_influence_list_view` routes orphan rows (whose
  `is_orphan` flag is True) to `superskin.select_orphan_bone_row` instead
  of the standard `superskin.select_vertex_group_row` — these operators must
  remain registered by the bones_tool operators package.
- **Adapter registry:** `BoneListAdapter` is registered under key ``'BONES'``
  in `shared/list_widget/select_ops._adapter_registry` at `ui.register()` time.
- **bl_idname stability:** `SUPERSKIN_OT_select_vertex_group_row`,
  `MESH_UL_influence_list_view`, and `SUPERSKIN_MT_bone_extra_overflow`
  are unchanged from their previous location in `ui/widget_deform_bones.py`.
