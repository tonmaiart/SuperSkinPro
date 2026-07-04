# CircleToolAdjust Domain Specification

## Domain Identity
- **Domain ID:** `circle_tool_adjust`
- **Actions:** `adjust_radius_interactive`
- **Tab:** `SKINNING`

## Architecture & Dataflow
1. User triggers Alt+Shift+RMB inside EDIT_MESH mode (`keymap.py`). This shortcut moved twice: originally plain Alt+LMB, then Alt+Ctrl+LMB, now Alt+Shift+RMB, each time to make room for a Weight Apply gesture shortcut (`features/weight_apply/keymap.py`) claiming the previous binding.
2. This invokes the `adjust_radius_interactive` action, which `CircleToolAdjustFeature.execute()` forwards to `bpy.ops.superskin.circle_tool_adjust_radius('INVOKE_DEFAULT')`.
3. `SUPERSKIN_OT_circle_tool_adjust_radius` (`ops.py`) modal captures mouse movement delta and updates `superskin_circle_tool_adjust_prefs.brush_radius_value` on the WindowManager. It records the triggering mouse button (`self._trigger_type`) at invoke and matches release against that button rather than a hardcoded one, since the bound button has changed more than once.
4. The `update` callback (`_on_radius_updated`) on `brush_radius_value` syncs the new value to Blender's native `view3d.select_circle` tool properties (clamped 1–300).

The N-panel slider in `draw_section()` also writes directly to `brush_radius_value`, triggering the same sync callback.

## File Manifest
- `circle_tool_adjust_feature.py`: `CircleToolAdjustFeature(UnifiedFeatureExtension)` — owns the `SSPrefCircleToolAdjust` PropertyGroup (`brush_radius_value`, min 1 / max 300 / default 30), action dispatch (`adjust_radius_interactive` → invokes the modal operator), UI slider, and JSON persistence (`default_radius` key).
- `ops.py`: `SUPERSKIN_OT_circle_tool_adjust_radius` (`superskin.circle_tool_adjust_radius`) — interactive modal operator tracking mouse movements.
- `keymap.py`: Registers the Alt+Shift+RMB shortcut for the modal operator.
- `default_config.json`: `default_radius` (30), `max_radius` (300), `min_radius` (1).
