"""Keymap registration for Weight Apply gesture shortcuts — owned by this feature package.

Shortcuts (Mesh Edit Mode):
  Alt+LMB  -> "add_scale" gesture (Add on positive drag, Scale on negative)
  Alt+RMB  -> "smooth_sharpen" gesture (Smooth on positive drag, Sharpen on negative)

Both bind to the same modal operator (`superskin.weight_gesture`, ops.py)
with a different `action` property. There is no plain-click apply -- only
holding and dragging the mouse registers anything. Dragging previews a
signed [-1.0, 1.0] value live on the mesh (0.0 = neutral start, sign picks
which of the two real actions runs, magnitude is its intensity), committing
on release. See ops.py:SUPERSKIN_OT_weight_gesture for the full interaction
contract, including why there is no mid-gesture cancel (release always
commits; undo is Ctrl+Z only).

Alt+LMB previously belonged to CircleToolAdjust (moved to Alt+Shift+RMB) and
Alt+RMB previously belonged to BonePicker's overlay-size adjust (moved to
Alt+Shift+MMB) -- both were changed in their own keymap.py to make room for
these.
"""

import bpy

_keymaps = []

_GESTURE_BINDINGS = (
    ("add_scale", 'LEFTMOUSE'),
    ("smooth_sharpen", 'RIGHTMOUSE'),
)


def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    for action, mouse_type in _GESTURE_BINDINGS:
        km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
        kmi = km.keymap_items.new(
            "superskin.weight_gesture",
            type=mouse_type,
            value='PRESS',
            alt=True,
        )
        kmi.properties.action = action
        _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
