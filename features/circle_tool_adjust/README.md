# CircleToolAdjust Domain Specification

## Domain Identity
- **Domain ID:** `circle_tool_adjust`
- **Actions:** `adjust_radius_interactive`

## Architecture & Dataflow
1. User triggers Alt+LMB inside EDIT_MESH mode.
2. `SUPERSKIN_OT_circle_tool_adjust_radius` modal captures mouse movement delta.
3. Delta is mapped to update `superskin_circle_tool_adjust_prefs.brush_radius_value` on the WindowManager.
4. The `update` callback on `brush_radius_value` syncs the new value to Blender's native circle select tool.

## File Manifest
- `prefs.py`: Owns the WindowManager PropertyGroup and PrefsExtensionSpec registration.
- `ops.py`: Implements the interactive modal operator tracking mouse movements.
- `keymap.py`: Registers the Alt+LMB shortcut for the modal operator.
- `circle_tool_adjust_domain.py`: DomainRegistry adapter binding domain ID and actions.
