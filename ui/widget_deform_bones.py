"""Deform Bone List drawing stub.

The UIList, adapter, row-click operator, overflow menu, and draw function
that previously lived here have been relocated to
``features/deform_bone_viewer/ui.py`` as part of the SKINNING tab domain
extraction (2026-06 architecture refactor).

That domain registers via ``PrefsExtensionRegistry`` and is drawn by
``ui/widget_preferences.py`` as the first non-collapsible entry in the
SKINNING tab.

This module is retained as an empty stub to avoid breaking any import
paths that still reference ``ui.widget_deform_bones``.
"""


def register():
    pass


def unregister():
    pass
