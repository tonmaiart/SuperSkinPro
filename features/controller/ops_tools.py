"""Tool operators for SuperSkinPro — SafeShrink.

OBJECT_OT_mw_copy_skin_weight_maya moved to weight_transfer/ops.py.
WM_OT_set_op_weight_preset moved to features/weight_apply/ops.py.

Relocated from operators/ops_tools.py to features/controller/ (2026-06).
"""

import bpy
import bmesh


# ==============================================================================
# SAFE SHRINK (from op_safe_shrink.py)
# ==============================================================================

class SUPERSKIN_OT_safe_shrink(bpy.types.Operator):
    bl_idname = "superskin.safe_shrink"
    bl_label = "Safe Shrink"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            selected = [v for v in bm.verts if v.select]

            if len(selected) <= 1:
                self.report({'WARNING'}, "Cannot shrink further — selection would vanish.")
                return {'FINISHED'}

            bpy.ops.mesh.select_less()
        return {'FINISHED'}


# ==============================================================================
# REGISTRATION
# ==============================================================================

def register():
    bpy.utils.register_class(SUPERSKIN_OT_safe_shrink)


def unregister():
    bpy.utils.unregister_class(SUPERSKIN_OT_safe_shrink)
