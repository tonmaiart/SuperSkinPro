"""Orphan bone row selection operator.

Selecting an orphan row sets active_orphan_name (not last_clicked_index,
since orphan bones have no real vertex group). Weight ops read
active_orphan_name via UIController._active_bone_name() and route through
get_unified_mapping() synthetic IDs so Rust can process them normally.

Relocated from core_subsystems/orphan_resolver/ops.py to eliminate a layering
violation (core_subsystems must not register bpy.types.Operator classes).
"""

import bpy


class SUPERSKIN_OT_select_orphan_bone_row(bpy.types.Operator):
    """Select an orphaned-bone row in the Deform Bones list.

    Sets active_orphan_name and clears last_clicked_index to -1.
    Weight ops (Add/Scale/Smooth/Sharpen) will target this orphan bone
    the same way they target a real bone.
    """
    bl_idname = "superskin.select_orphan_bone_row"
    bl_label = "Select Orphaned Bone Row"
    bl_options = {'INTERNAL'}

    orphan_name: bpy.props.StringProperty(name="Orphaned Bone Name")

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        storage = obj.superskin_storage
        storage.active_orphan_name = self.orphan_name
        storage.last_clicked_index = -1
        _sync_bones_idx_to_orphan(obj, self.orphan_name)
        context.area.tag_redraw()
        return {'FINISHED'}


def _sync_bones_idx_to_orphan(obj, orphan_name: str):
    """Point superskin_bones_idx at the orphan row in the mirror collection."""
    for i, item in enumerate(obj.superskin_bones_collection):
        if item.is_orphan and item.name == orphan_name:
            obj.superskin_bones_idx = i
            return


_classes = (SUPERSKIN_OT_select_orphan_bone_row,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
