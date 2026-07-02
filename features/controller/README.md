# Controller Domain

## Domain Identity

- **Domain ID:** `controller`
- **Actions:** *(none — structural/utility-only domain)*
- **Tab:** `SKINNING` (registered, but `draw_section()` is a no-op — no N-panel UI content is rendered)

## Responsibility

Owns all cross-cutting control operators that are not tied to a specific
weight-painting feature:

| Sub-module | Contents |
|---|---|
| `ops_scene_modes.py` | Enter/Exit/Toggle Edit Mode, Force Pose Mode, Enter Layer Edit, Save Weights, auto-save guard handler, temp-VG helpers |
| `ops_shortcuts.py` | Pie menu (`MW_MT_pie_menu`, `MW_OT_call_pie`) and keymap registration |
| `ops_tools.py` | `SUPERSKIN_OT_safe_shrink` |
| `controller_feature.py` | `ControllerFeature(UnifiedFeatureExtension)` — structural registry entry only, no actions and no draw content |

## Architecture Notes

- No action dispatching occurs — `ControllerFeature.execute()` always returns
  `{"status": "CANCELLED"}` and is never actually called. The registry entry
  exists purely so the domain is registered under `UnifiedRegistry`; all real
  behaviour is wired up directly from `__init__.py` via the `ops_*` sub-modules.
- The auto-save guard (`_superskin_auto_save_guard`) is a
  `@bpy.app.handlers.persistent` callback registered in `ops_scene_modes.register()`
  and removed in `ops_scene_modes.unregister()`.
- Keymaps are registered inline in `ops_shortcuts.register()` and cleaned up in
  `ops_shortcuts.unregister()` via the `addon_keymaps` list.
- `_enter_edit_mode` / `_exit_edit_mode` are module-level helpers shared by
  multiple operator classes within `ops_scene_modes.py`; they must not be
  imported from outside this package.
- `superskin.enter_layer_edit` (defined in `ops_scene_modes.py`) is referenced
  by `bl_idname` string from `features/layer_viewer/layer_viewer_feature.py`'s
  UI layout — a string reference, not a Python import, so it does not violate
  the Zero Cross-Imports rule between feature packages.
