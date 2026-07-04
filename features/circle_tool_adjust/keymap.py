"""Keymap registration for CircleToolAdjust — owned by this feature package.

Shortcuts:
  Alt+Shift+RMB (Mesh mode) -> invoke radius adjustment modal

The original Alt+LMB binding was moved to Alt+Ctrl+LMB (when Alt+LMB became
the Weight Apply "add_scale" gesture), then moved again to Alt+Shift+RMB once
Alt+RMB became the Weight Apply "smooth_sharpen" gesture
(features/weight_apply/keymap.py) -- Alt+Shift+RMB was free since Sharpen no
longer has its own dedicated shortcut.
"""

import bpy

_keymaps = []


def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
    kmi = km.keymap_items.new(
        "superskin.circle_tool_adjust_radius",
        type='RIGHTMOUSE',
        value='PRESS',
        alt=True,
        shift=True,
    )
    _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
