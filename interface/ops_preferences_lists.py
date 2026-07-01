"""Scrollable UIList classes for Preferences collections that can grow without
bound (ramp stops via "Add Stop", mirror search/replace pairs via "Add Pair").

Plain ``template_list`` rows with no filtering or multi-select — unlike the
sealed ``ui/list_widget`` package that backs the bones/layers domains, these
only need a fixed visible-row count so the popup height stops scaling with
user data; everything beyond ``rows`` scrolls instead. Add/remove/move stay
as the existing operators in ``ops_preferences.py``, driven by each list's
``active_index`` (set by clicking a row).
"""

import bpy


class SUPERSKIN_UL_ramp_stops(bpy.types.UIList):
    bl_idname = "SUPERSKIN_UL_ramp_stops"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "position", text="")
        row.prop(item, "color", text="")


_classes = [
    SUPERSKIN_UL_ramp_stops,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
