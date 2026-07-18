"""Keymap registration for DeformBoneViewer — owned by this feature package.

Shortcuts:
  Alt+Ctrl+MMB (Mesh mode) -> `object.mw_select_affect_vertices`
    ("Select Affect Vertices" -- already the sidebar button in
    `ui.py::draw_influence_list_system()`'s `button_defs`; see `ops.py` for
    the operator itself). Plain mode: every vertex with weight/mask > 0.
  Alt+Ctrl+RMB (Mesh mode) -> `object.mw_select_affect_boundary` -- a
    separate operator that selects vertices sitting at the boundary/
    junction between the unweighted (0) and weighted region instead (any
    vertex whose own weight-state differs from at least one mesh
    neighbor's). Deliberately a distinct operator with no adjustable
    properties, rather than a property flag on the operator above, so
    neither shortcut shows a redo/options popup at the bottom-left.

Both entries reference their operator by its `bl_idname` string like every
other keymap.py in this codebase (not a Python import), so this doesn't
violate Zero Cross-Imports even for callers outside this package.
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
        "object.mw_select_affect_vertices",
        type='MIDDLEMOUSE',
        value='PRESS',
        alt=True,
        ctrl=True,
    )
    _keymaps.append((km, kmi))

    km = kc.keymaps.new(name='Mesh', space_type='EMPTY')
    kmi = km.keymap_items.new(
        "object.mw_select_affect_boundary",
        type='RIGHTMOUSE',
        value='PRESS',
        alt=True,
        ctrl=True,
    )
    _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
