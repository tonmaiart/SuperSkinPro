"""Mirror domain operators — presentation/dispatch only.

Core orchestration lives in features/mirror/logic.py (execute_mirror_pipeline()).
Rust math lives in mirror/logic.py.
PropertyGroups, MirrorPreferencesService, and UI drawing live in mirror_feature.py.
"""

import bpy
from ...core.facade import CoreFacade
from .logic import generate_pairs, get_bone_centers, execute_mirror_pipeline
from .mirror_feature import MirrorPreferencesService


# ==============================================================================
# MIRROR WEIGHTS
# ==============================================================================

class OBJECT_OT_MirrorWeights(bpy.types.Operator):
    """Mirror skin weights using ngSkinTools-style name matching."""
    bl_idname = "object.mirror_weights"
    bl_label = "Mirror Weights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH')

    def execute(self, context):
        facade = CoreFacade(context)
        try:
            is_mask = facade.is_mask_context()
            both_data = MirrorPreferencesService.get_mirror_both_data()
            do_mask = is_mask or both_data
            do_layer = (not is_mask) or both_data

            if do_layer and not do_mask:
                # Bone-only mirror: warn early if nothing would happen at all.
                # (skip this check when both_data is on — mask channel still
                # mirrors successfully even if the bone side has no pairs)
                sr_raw = MirrorPreferencesService.get_mirror_search_replace_pairs()
                pairs = generate_pairs(
                    vg_names=[vg.name for vg in facade.get_vertex_groups()],
                    bone_centers=get_bone_centers(facade),
                    sr_list=sr_raw,
                    axis=MirrorPreferencesService.get_mirror_axis(),
                    direction=MirrorPreferencesService.get_mirror_direction(),
                )
                if not pairs:
                    self.report({'WARNING'}, "No mirror pairs found.")
                    return {'CANCELLED'}
        except ValueError:
            return {'CANCELLED'}

        context.scene.superskin_internal_transaction = True
        try:
            execute_mirror_pipeline(facade)
        except ValueError:
            return {'CANCELLED'}
        finally:
            context.scene.superskin_internal_transaction = False
        return {'FINISHED'}


# ==============================================================================
# MIRROR SEARCH/REPLACE PAIR MANAGEMENT
# ==============================================================================

class SUPERSKIN_UL_mirror_sr(bpy.types.UIList):
    bl_idname = "SUPERSKIN_UL_mirror_sr"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "search_text", text="")
        row.prop(item, "replace_text", text="")


class SUPERSKIN_OT_add_mirror_sr(bpy.types.Operator):
    """Add a new bone-name search/replace pair to the Mirror tab."""
    bl_idname = "superskin.add_mirror_sr"
    bl_label = "Add Mirror Search/Replace Pair"
    bl_options = {'REGISTER'}

    def execute(self, context):
        mirror = context.window_manager.superskin_mirror_prefs
        sr_coll = mirror.search_replace_pairs
        sr_coll.add()
        mirror.search_replace_index = len(sr_coll) - 1
        CoreFacade.save_prefs()
        return {'FINISHED'}


class SUPERSKIN_OT_remove_mirror_sr(bpy.types.Operator):
    """Remove a bone-name search/replace pair from the Mirror tab at the given index."""
    bl_idname = "superskin.remove_mirror_sr"
    bl_label = "Remove Mirror Search/Replace Pair"
    bl_options = {'REGISTER'}

    index: bpy.props.IntProperty(
        name="Index",
        description="Index of the pair to remove",
        default=0,
        min=0,
    )

    def execute(self, context):
        mirror = context.window_manager.superskin_mirror_prefs
        sr_coll = mirror.search_replace_pairs
        if 0 <= self.index < len(sr_coll):
            sr_coll.remove(self.index)
        mirror.search_replace_index = max(0, min(mirror.search_replace_index, len(sr_coll) - 1))
        CoreFacade.save_prefs()
        return {'FINISHED'}


# ==============================================================================
# REGISTRATION
# ==============================================================================

_classes = (
    OBJECT_OT_MirrorWeights,
    SUPERSKIN_UL_mirror_sr,
    SUPERSKIN_OT_add_mirror_sr,
    SUPERSKIN_OT_remove_mirror_sr,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
