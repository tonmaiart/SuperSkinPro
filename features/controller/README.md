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
| `ops_scene_modes.py` | Enter/Exit/Toggle Edit Mode, Force Pose Mode (now bakes temp VGs via `_exit_edit_mode` before bouncing Mesh→Armature, see below), Popup Main Panel, Enter Layer Edit, Save Weights, auto-save guard handler, temp-VG helpers |
| `ops_shortcuts.py` | Pie menu (`MW_MT_pie_menu`, `MW_OT_call_pie`) and keymap registration |
| `ops_tools.py` | `SUPERSKIN_OT_safe_shrink` (no longer wired into the pie menu, see below) |
| `controller_feature.py` | `ControllerFeature(UnifiedFeatureExtension)` — structural registry entry only, no actions and no draw content |

## Pie Menu (`ops_shortcuts.py`)

- **Non-`EDIT_MESH` context:** `object.mw_popup_main_panel` ("Popup Main
  Panel") only reveals the SuperSkinPro sidebar (`force_open_super_skin_tab()`)
  — it no longer routes through `object.mw_toggle_edit_mode` and no longer
  auto-enters Edit Layer Weight. `object.mw_force_pose_mode` ("Enter Pose
  Mode") is unchanged in this branch.
- **`EDIT_MESH` context:** `superskin.save_weight_and_exit` ("Save & Enter
  Object Mode") is called directly — the same `deform_bone_viewer` "Save
  Weights & Exit" command, referenced by `bl_idname` string only (Zero
  Cross-Imports). `object.mw_force_pose_mode` ("Save & Enter Pose Mode")
  now bakes the active layer before switching to Pose Mode (see below).
  `Grow`/`Shrink`/`Toggle X-Ray` slots were removed; `object.mirror_weights`
  ("Mirror Skin Weight") is unchanged. Pie-slot ordering intentionally keeps
  the mode-toggle button and the pose-mode button in the same radial
  position across both branches (3 leading separators padding the slots
  that used to hold Grow/Shrink/the extra separator).
- `object.mw_toggle_edit_mode` and `superskin.safe_shrink` remain registered
  (other code may still reference them) but are no longer invoked from the
  pie menu.

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
- `_enter_edit_mode()` no longer force-switches the active tool to
  `builtin.select_circle` on entry. This is the single shared entry point
  used by `superskin.enter_layer_edit` (`layer_viewer`'s "Enter Layer Edit"
  button) and by the Deform Bones viewer's Edit Mode flow, so the tool
  choice is left as whatever the user already had active.
