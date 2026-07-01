"""WeightApplyFeature — Unified Component Architecture implementation for the weight_apply domain.

Collapses the old WeightApplyDomain (action dispatch) and prefs.py (PropertyGroup,
draw, persistence) into a single UnifiedFeatureExtension subclass.

Owns:
  - SSPrefWeightApply PropertyGroup (registered on WindowManager)
  - WeightApplyPreferencesService (stateless accessor)
  - Action dispatch: add, scale, smooth, sharpen
  - UI layout: draw_section()
  - JSON persistence: populate() / serialize_into()
"""

import bpy
import os

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


# ==============================================================================
# Property Groups
# ==============================================================================

def _on_intensity_changed(self, context):
    from ...core.facade import CoreFacade
    CoreFacade.save_prefs()


class SSPrefWeightApply(bpy.types.PropertyGroup):
    """Weight-apply intensity settings (per-machine)."""
    add_val: bpy.props.FloatProperty(
        name="Add", min=0.0, max=1.0, default=0.61,
        update=_on_intensity_changed,
    )
    scale_val: bpy.props.FloatProperty(
        name="Scale", min=0.0, max=1.0, default=0.61,
        update=_on_intensity_changed,
    )
    smooth_val: bpy.props.FloatProperty(
        name="Smooth", min=0.0, max=1.0, default=0.61,
        update=_on_intensity_changed,
    )
    sharpen_val: bpy.props.FloatProperty(
        name="Sharpen", min=0.0, max=1.0, default=0.61,
        update=_on_intensity_changed,
    )
    smooth_affected_only: bpy.props.BoolProperty(
        name="Smooth Affected Only",
        description="Limit smoothing to vertices that already have weight > 0",
        default=False,
        update=_on_intensity_changed,
    )


# ==============================================================================
# Preferences accessor (replaces the old get_prefs() in prefs.py)
# ==============================================================================

class WeightApplyPreferencesService:
    """Stateless accessor for weight-apply prefs — consumed by logic.py and ui.py."""

    @staticmethod
    def get_prefs() -> "SSPrefWeightApply":
        return bpy.context.window_manager.superskin_weight_apply_prefs


# Backward-compat alias so `from .weight_apply_feature import get_prefs` works
get_prefs = WeightApplyPreferencesService.get_prefs


# ==============================================================================
# WeightApplyFeature — UnifiedFeatureExtension
# ==============================================================================

class WeightApplyFeature(UnifiedFeatureExtension):
    """Unified extension for the Weight Apply domain."""

    # ── Configuration (class attributes) ───────────────────────────────────

    domain_id = "weight_apply"
    actions = ["add", "scale", "smooth", "sharpen"]
    section_title = "Apply"
    draw_tab = "SKINNING"
    defaults_path = _DEFAULTS_PATH
    priority = 1
    expanded_by_default = True
    
    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        from .logic import apply_add, apply_scale, apply_smooth, apply_sharpen

        p = get_prefs()
        is_mask = core_facade.is_mask_context()
        active_vg_id = core_facade.get_active_vg_id()

        layer_str = core_facade.read_active_layer()
        bone_to_id, id_to_bone = core_facade.get_unified_mapping()
        layer_int = {
            v_idx: {bone_to_id[b]: w for b, w in weights.items() if b in bone_to_id}
            for v_idx, weights in layer_str.items()
        }
        mask_dict = core_facade.get_active_mask_dict()
        locks_id = core_facade.get_locks_by_id()
        selected = core_facade.get_selected_verts()

        if action == "add":
            if active_vg_id is None and not is_mask:
                return {"status": "CANCELLED", "message": "No active bone"}
            res_layer, res_mask = apply_add(
                layer_int, mask_dict, selected,
                active_vg_id if active_vg_id is not None else -1,
                p.add_val, locks_id,
                core_facade.get_active_layer_index(), is_mask,
            )

        elif action == "scale":
            if active_vg_id is None and not is_mask:
                return {"status": "CANCELLED", "message": "No active bone"}
            res_layer, res_mask = apply_scale(
                layer_int, mask_dict, selected,
                active_vg_id if active_vg_id is not None else -1,
                p.scale_val, locks_id, is_mask,
            )

        elif action == "smooth":
            res_layer, res_mask = apply_smooth(
                layer_int, mask_dict, selected,
                core_facade.get_cached_mesh_neighbors(),
                p.smooth_val, locks_id,
                p.smooth_affected_only, is_mask,
            )

        elif action == "sharpen":
            if active_vg_id is None and not is_mask:
                return {"status": "CANCELLED", "message": "No active bone"}
            res_layer, res_mask = apply_sharpen(
                layer_int, mask_dict, selected,
                core_facade.get_cached_mesh_neighbors(),
                active_vg_id if active_vg_id is not None else -1,
                p.sharpen_val, is_mask,
            )

        else:
            return {"status": "CANCELLED", "message": f"Unknown action: {action}"}

        if is_mask:
            # Merge the Rust-modified vertices back into the full baseline mask so
            # non-selected vertices keep their existing mask values.  Rust returns
            # only the selected vertices in res_mask; writing it directly would clear
            # every other vertex's mask to 0.
            full_mask = dict(mask_dict)
            full_mask.update(res_mask)
            # Use the ctrl escape with is_mask_mode=True to bypass the bone
            # normalization loop, which would otherwise prune unselected vertices.
            ctrl = core_facade.get_ctrl()
            ctrl._write_active_layer_string(res_layer, id_to_bone,
                                            full_mask, is_mask_mode=True)
            core_facade.finish(color_only=True)
        else:
            res_layer_str = {
                v_idx: {id_to_bone[b]: w for b, w in weights.items() if b in id_to_bone}
                for v_idx, weights in res_layer.items()
            }
            core_facade.write_active_layer(res_layer_str, color_only=True)

        return {"status": "FINISHED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Draw the full Weight Apply section: Add, Scale, Smooth, Sharpen controls."""
        from .ui import draw_section
        draw_section(layout)

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """Write section data dict into the live WindowManager property."""
        p = get_prefs()
        p.add_val = float(data.get("add_val", 0.61))
        p.scale_val = float(data.get("scale_val", 0.61))
        p.smooth_val = float(data.get("smooth_val", 0.61))
        p.sharpen_val = float(data.get("sharpen_val", 0.61))
        p.smooth_affected_only = bool(data.get("smooth_affected_only", False))

    def serialize_into(self, full_dict: dict) -> None:
        """Write current values into full_dict at the correct JSON path."""
        p = get_prefs()
        full_dict["weight_apply"] = {
            "add_val": p.add_val,
            "scale_val": p.scale_val,
            "smooth_val": p.smooth_val,
            "sharpen_val": p.sharpen_val,
            "smooth_affected_only": p.smooth_affected_only,
        }


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register PropertyGroups on WindowManager and the extension with UnifiedRegistry."""
    bpy.utils.register_class(SSPrefWeightApply)
    bpy.types.WindowManager.superskin_weight_apply_prefs = bpy.props.PointerProperty(
        type=SSPrefWeightApply, options={'SKIP_SAVE'},
    )
    UnifiedRegistry.register(WeightApplyFeature())


def unregister():
    """Unregister PropertyGroups and the extension."""
    UnifiedRegistry.unregister("weight_apply")
    try:
        del bpy.types.WindowManager.superskin_weight_apply_prefs
    except Exception:
        pass
    bpy.utils.unregister_class(SSPrefWeightApply)
