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
import time

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade
from ...core_subsystems.debug_logging import DebugLogService

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
    smooth_across_surface: bpy.props.BoolProperty(
        name="Smooth Across Surface",
        description=(
            "Expand the smoothing neighborhood using surface (geodesic) distance "
            "instead of raw vertex adjacency, so results stay consistent across "
            "areas with uneven topology density"
        ),
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

    def snapshot_context(self, core_facade: CoreFacade) -> dict:
        """Read everything an apply action needs to compute from, once.

        Used both by the single-shot `execute()` path and by the gesture
        modal operator (`ops.py:SUPERSKIN_OT_weight_gesture`). The gesture
        operator re-runs `apply_action()` on every mouse-move at a changing
        intensity, and must always compute from this same fixed baseline —
        recomputing from `core_facade` fresh each move would apply on top of
        the previous preview's result and compound instead of preview.
        """
        is_mask = core_facade.is_mask_context()
        active_vg_id = core_facade.get_active_vg_id()
        layer_str = core_facade.read_active_layer()
        bone_to_id, id_to_bone = core_facade.get_unified_mapping()
        layer_int = {
            v_idx: {bone_to_id[b]: w for b, w in weights.items() if b in bone_to_id}
            for v_idx, weights in layer_str.items()
        }
        return {
            "is_mask": is_mask,
            "active_vg_id": active_vg_id,
            "layer_int": layer_int,
            "id_to_bone": id_to_bone,
            "mask_dict": core_facade.get_active_mask_dict(),
            "locks_id": core_facade.get_locks_by_id(),
            "selected": core_facade.get_selected_verts(),
        }

    def apply_action(self, action: str, core_facade: CoreFacade, ctx: dict,
                     intensity: float, *, affected_only: bool = None) -> dict:
        """Compute `action` from the `ctx` baseline (see `snapshot_context()`)
        at `intensity`, then write the result. Never mutates `ctx`, so it is
        safe to call repeatedly from the same snapshot (gesture drag preview)
        without compounding."""
        from .logic import (
            apply_add, apply_scale, apply_smooth, apply_sharpen,
            build_surface_neighbors, SHARPEN_RADIUS_MULTIPLIER,
        )

        p = get_prefs()
        is_mask = ctx["is_mask"]
        active_vg_id = ctx["active_vg_id"]
        id_to_bone = ctx["id_to_bone"]
        selected = ctx["selected"]
        locks_id = ctx["locks_id"]

        # dirty_verts: every vertex this tick's write could possibly touch --
        # always a superset of `selected`, widened for smooth/sharpen by
        # whichever neighbor set Rust is about to read below. Built from the
        # exact same `neighbors` dict used for the Rust call, never a
        # separately re-derived approximation, so it can't under-cover what
        # Rust actually changes. Passed to the write calls below to let the
        # core flatten pipeline skip full-mesh BMesh scans on this hot path.
        dirty_verts = set(selected)
        neighbors = None
        if action == "smooth":
            if p.smooth_across_surface:
                neighbors = build_surface_neighbors(core_facade, selected)
            else:
                neighbors = core_facade.get_cached_mesh_neighbors()
        elif action == "sharpen":
            neighbors = build_surface_neighbors(
                core_facade, selected, radius_multiplier=SHARPEN_RADIUS_MULTIPLIER,
            )
        if neighbors is not None:
            for v in selected:
                dirty_verts.update(neighbors.get(v, ()))

        # Only feed Rust the vertices it could possibly touch (dirty_verts) --
        # every rust_*_logic function's write set is exactly `selected`, and
        # its only reads outside `selected` are neighbor lookups (sharpen/
        # smooth) that dirty_verts already guarantees are present. This keeps
        # the Python<->Rust FFI marshaling cost proportional to brush size,
        # not total painted-vertex count on the mesh.
        #
        # CRITICAL: the return values are named `res_layer_diff`/`res_mask_diff`
        # (never `res_layer`/`res_mask`) specifically so it's structurally
        # obvious they are NOT a complete active-layer snapshot -- merge them
        # into `full_layer_int` below and use ONLY that downstream. Passing
        # the small diff anywhere a complete dict is expected reproduces the
        # exact "untouched vertex's weight-paint color goes black" bug
        # already hit and fixed once this session (see git history / prior
        # session notes on write_layer_to_temp_vgs_bm's "absence = clear"
        # semantics, and flatten_to_mesh_edit()'s active_layer_override
        # contract, and ss_layer_N's direct-persistence path -- all three
        # require the complete layer, not a subset).
        layer_int_for_rust = {v: dict(ctx["layer_int"].get(v, {})) for v in dirty_verts}
        mask_dict_for_rust = {v: ctx["mask_dict"][v] for v in dirty_verts if v in ctx["mask_dict"]}
        mask_dict = dict(ctx["mask_dict"])

        # Profiling: gated by the same lazy-guard pattern as debug logging --
        # time.perf_counter() calls themselves are cheap, but keep this
        # opt-in (enable the "feature_domains" debug category in Preferences
        # to see per-tick ms in the console) rather than always-on.
        _profile = DebugLogService.is_enabled("feature_domains")
        _t0 = time.perf_counter() if _profile else None

        if action == "add":
            if active_vg_id is None and not is_mask:
                return {"status": "CANCELLED", "message": "No active bone"}
            res_layer_diff, res_mask_diff = apply_add(
                layer_int_for_rust, mask_dict_for_rust, selected,
                active_vg_id if active_vg_id is not None else -1,
                intensity, locks_id,
                core_facade.get_active_layer_index(), is_mask,
            )

        elif action == "scale":
            if active_vg_id is None and not is_mask:
                return {"status": "CANCELLED", "message": "No active bone"}
            res_layer_diff, res_mask_diff = apply_scale(
                layer_int_for_rust, mask_dict_for_rust, selected,
                active_vg_id if active_vg_id is not None else -1,
                intensity, locks_id, is_mask,
            )

        elif action == "smooth":
            res_layer_diff, res_mask_diff = apply_smooth(
                layer_int_for_rust, mask_dict_for_rust, selected,
                neighbors,
                intensity, locks_id,
                p.smooth_affected_only if affected_only is None else affected_only,
                is_mask,
            )

        elif action == "sharpen":
            if active_vg_id is None and not is_mask:
                return {"status": "CANCELLED", "message": "No active bone"}
            res_layer_diff, res_mask_diff = apply_sharpen(
                layer_int_for_rust, mask_dict_for_rust, selected,
                neighbors,
                active_vg_id if active_vg_id is not None else -1,
                intensity, is_mask,
            )

        else:
            return {"status": "CANCELLED", "message": f"Unknown action: {action}"}

        if _profile:
            _t_rust = time.perf_counter()

        # Merge the small Rust diff into a full copy of the baseline -- this
        # (not res_layer_diff) is what every downstream consumer below uses.
        full_layer_int = {v: dict(w) for v, w in ctx["layer_int"].items()}
        full_layer_int.update(res_layer_diff)

        if _profile:
            _t_merge = time.perf_counter()

        if is_mask:
            # Merge the Rust-modified vertices back into the full baseline mask so
            # non-selected vertices keep their existing mask values.  Rust returns
            # only the selected vertices in res_mask_diff; writing it directly
            # would clear every other vertex's mask to 0.
            full_mask = dict(ctx["mask_dict"])
            full_mask.update(res_mask_diff)
            # Use the ctrl escape with is_mask_mode=True to bypass the bone
            # normalization loop, which would otherwise prune unselected vertices.
            ctrl = core_facade.get_ctrl()
            ctrl._write_active_layer_string(full_layer_int, id_to_bone,
                                            full_mask, is_mask_mode=True,
                                            dirty_verts=dirty_verts)
            core_facade.finish(color_only=True, dirty_verts=dirty_verts)
        elif core_facade.get_obj().mode == 'EDIT':
            # write_active_layer_from_calc() takes Rust's int-keyed output
            # directly, skipping the int->string->int round-trip
            # write_active_layer() would otherwise do, and already flattens +
            # redraws inline for EDIT mode -- no separate finish() call needed
            # (calling one here would flatten a second time).
            # mask_override=mask_dict: non-mask actions never modify the mask
            # (Rust only mutates it when is_mask_mode=True), so this tick's
            # mask_dict is still the correct, current one -- passing it lets
            # the compositor skip re-reading it from the BMesh too.
            core_facade.write_active_layer_from_calc(
                full_layer_int, id_to_bone, dirty_verts=dirty_verts, mask_override=mask_dict,
            )
        else:
            # write_active_layer_from_calc()'s Object-Mode branch only saves
            # to storage and does not flatten/redraw, so Object Mode keeps the
            # slower string round-trip path (which calls finish() internally).
            res_layer_str = {
                v_idx: {id_to_bone[b]: w for b, w in weights.items() if b in id_to_bone}
                for v_idx, weights in full_layer_int.items()
            }
            core_facade.write_active_layer(res_layer_str, color_only=True, dirty_verts=dirty_verts)

        if _profile:
            _t_write = time.perf_counter()
            DebugLogService.log(
                "feature_domains",
                f"apply_action({action!r}) dirty_verts={len(dirty_verts)}: "
                f"rust={1000 * (_t_rust - _t0):.2f}ms "
                f"merge={1000 * (_t_merge - _t_rust):.2f}ms "
                f"write={1000 * (_t_write - _t_merge):.2f}ms "
                f"total={1000 * (_t_write - _t0):.2f}ms",
            )

        return {"status": "FINISHED"}

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        p = get_prefs()
        core_facade.debug_log(
            "feature_domains",
            f"weight_apply.execute() action={action!r}",
        )

        ctx = self.snapshot_context(core_facade)
        intensity = {
            "add": p.add_val, "scale": p.scale_val,
            "smooth": p.smooth_val, "sharpen": p.sharpen_val,
        }.get(action, 0.0)
        result = self.apply_action(action, core_facade, ctx, intensity)

        core_facade.debug_log("feature_domains", f"weight_apply.execute() action={action!r} done")
        return result

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
        p.smooth_across_surface = bool(data.get("smooth_across_surface", False))

    def serialize_into(self, full_dict: dict) -> None:
        """Write current values into full_dict at the correct JSON path."""
        p = get_prefs()
        full_dict["weight_apply"] = {
            "add_val": p.add_val,
            "scale_val": p.scale_val,
            "smooth_val": p.smooth_val,
            "sharpen_val": p.sharpen_val,
            "smooth_affected_only": p.smooth_affected_only,
            "smooth_across_surface": p.smooth_across_surface,
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
