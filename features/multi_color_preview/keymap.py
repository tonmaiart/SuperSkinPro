"""Keymap registration for multi_color_preview — Alt+3 binds to
toggle_multi_color, now a hold gesture: `value='PRESS'` still invokes it as
before, but the operator itself is a modal that starts the preview on
invoke and stops it on releasing Alt+3, rather than a one-shot toggle. See
ops.py:SUPERSKIN_OT_toggle_multi_color."""

import bpy

_keymaps = []


def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
    kmi = km.keymap_items.new(
        "superskin.toggle_multi_color", type='THREE', value='PRESS', alt=True)
    _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
