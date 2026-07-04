# Bone Picker Domain Specification

Manages the interactive bone selection tool (Modal Operator Alt+2) and the persistent diamond wedge skeleton overlay in the 3D viewport.

## ⚙️ Domain Actions Matrix

| Action | Purpose |
|---|---|
| `start_bone_picker` | Invokes the modal viewport raycast ray-selection loop. |
| `stop_bone_picker` | Tears down draw handlers and cleanly exits picker modal context. |
| `clear_multi_selection`| Flushes the multi-selection bone pool on the active mesh object. |
*Operators: `object.mw_pick_bone` (Modal), `superskin.toggle_color_bone_style` (redirects to multi_color_preview domain), `superskin.clear_multi_selection`, `superskin.toggle_deform_bone_overlay`, `superskin.adjust_bone_overlay_size` (Modal, see below).*

## 🖱️ Overlay Size Adjust (`Alt+Shift+MMB`)

`SUPERSKIN_OT_adjust_bone_overlay_size` (`ops.py`) is a hold+drag modal that
live-adjusts `superskin_bone_picker_prefs.overall_size` (clamped `0.1`-`5.0`,
`+= delta * 0.01` per `MOUSEMOVE`). It records the triggering mouse button
(`self._trigger_type`) at invoke and matches release against that button
rather than a hardcoded one, since the bound button has changed over time.
`ESC` reverts to the value backed up at invoke; release commits.

Shortcut history: originally plain `Alt+RMB`, moved to `Alt+Shift+MMB`
because `Alt+RMB` became the Weight Apply `smooth_sharpen` gesture shortcut
(`features/weight_apply/keymap.py`). See `keymap.py`'s own docstring for the
full shortcut table (`Alt+2`, `Alt+Shift+2`, `Alt+3`, `Alt+Shift+MMB`).

## 🛠️ Configuration Spec (`default_config.json`)
```json
{
  "static_active_color":  [1.0, 0.15, 0.15, 1.0],
  "static_multi_color":   [0.0, 0.3,  0.75, 0.9],
  "static_default_color": [0.35, 0.65, 1.0, 0.35],
  "hover_color":          [1.0, 0.55, 0.0,  1.0],
  "static_wedge_width":   5.0,
  "static_line_width":    1,
  "hover_line_width":     2,
  "hold_line_width":      3,
  "overall_size":          1.0,
  "pivot_ratio":          0.333,
  "fill_opacity":         0.25,
  "head_circle_size":     0.55
}
```
Note: `SSPrefBonePicker.tail_circle_size` (default `0.36`) is a registered PropertyGroup field not currently present in `default_config.json`.