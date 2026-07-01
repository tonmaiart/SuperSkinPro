"""Keymap registration for CircleToolAdjust — owned by this feature package.

Shortcuts:
  Alt+LMB (Mesh mode) → invoke radius adjustment modal
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
        type='LEFTMOUSE',
        value='PRESS',
        alt=True,
    )
    _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
