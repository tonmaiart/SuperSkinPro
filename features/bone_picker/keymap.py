"""Bone Picker keymap registration — owned by the bone_picker feature package.

Shortcuts:
  Alt+2            → invoke bone picker modal (stays open until explicitly cancelled)
  Alt+Shift+2      → toggle deform bone overlay visibility
  Alt+3            → toggle color bone style
  Alt+Shift+MMB    → adjust bone overlay size (hold + drag)

Alt+Shift+MMB previously was plain Alt+RMB, moved here because Alt+RMB
became the Weight Apply "smooth_sharpen" gesture shortcut
(features/weight_apply/keymap.py). `SUPERSKIN_OT_adjust_bone_overlay_size`
(ops.py) records the triggering mouse button at invoke and matches release
against that button rather than a hardcoded one, since the bound button has
changed.

Inside the modal:
  Left click / drag  → sweep add to multi selection
  Right click on bone → remove bone from multi selection
  Right click empty  → cancel / revert
  Release 2          → confirm single select (hovered bone), exit
  ESC                → cancel / revert
"""

import bpy

_keymaps = []


def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
    kmi = km.keymap_items.new("superskin.toggle_deform_bone_overlay", type='TWO', value='PRESS', alt=True, shift=True)
    _keymaps.append((km, kmi))

    km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
    kmi = km.keymap_items.new("object.mw_pick_bone", type='TWO', value='PRESS', alt=True)
    _keymaps.append((km, kmi))

    km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
    kmi = km.keymap_items.new(
        "superskin.adjust_bone_overlay_size", type='MIDDLEMOUSE', value='PRESS', alt=True, shift=True,
    )
    _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
