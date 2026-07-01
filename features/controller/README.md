# Controller Domain

## Domain Identity

- **Domain ID:** `controller`
- **Actions:** *(none — utility-only domain)*
- **Tab:** N/A (no PrefsExtensionSpec)

## Responsibility

Owns all cross-cutting control operators that are not tied to a specific
weight-painting feature:

| Sub-module | Contents |
|---|---|
| `ops_scene_modes.py` | Enter/Exit/Toggle Edit Mode, Force Pose Mode, Enter Layer Edit, Save Weights, auto-save guard handler, temp-VG helpers |
| `ops_shortcuts.py` | Pie menu (`MW_MT_pie_menu`, `MW_OT_call_pie`) and keymap registration |
| `ops_tools.py` | `SUPERSKIN_OT_safe_shrink` |
| `controller_domain.py` | `BaseDomain` stub — satisfies DomainRegistry contract |

## Architecture Notes

- No DomainRegistry dispatching occurs — `ControllerDomain.execute()` is never
  called. The DomainRegistry entry is structural only.
- The auto-save guard (`_superskin_auto_save_guard`) is a
  `@bpy.app.handlers.persistent` callback registered in `ops_scene_modes.register()`
  and removed in `ops_scene_modes.unregister()`.
- Keymaps are registered inline in `ops_shortcuts.register()` and cleaned up in
  `ops_shortcuts.unregister()` via the `addon_keymaps` list.
- `_enter_edit_mode` / `_exit_edit_mode` are module-level helpers shared by
  multiple operator classes within `ops_scene_modes.py`; they must not be
  imported from outside this package.
