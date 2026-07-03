"""BonePickerFeature — Unified Component Architecture implementation for the bone picker domain.

Collapses the old BonePickerDomain (action dispatch) and prefs.py (PropertyGroup,
draw, persistence) into a single UnifiedFeatureExtension subclass.

Owns:
  - SSPrefBonePicker PropertyGroup (registered on WindowManager)
  - Action dispatch: "start_bone_picker", "stop_bone_picker", "clear_multi_selection"
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

def _on_changed(self, context):
    if not getattr(context, 'active_object', None):
        return
    from ...core.facade import CoreFacade
    try:
        CoreFacade(context).invalidate_color_only()
    except ValueError:
        pass  # Not activated -- nothing to redraw, the sidebar panel is hidden anyway.
    CoreFacade.save_prefs()


class SSPrefBonePicker(bpy.types.PropertyGroup):
    """Visual settings for the static deform skeleton overlay."""

    static_active_color: bpy.props.FloatVectorProperty(
        name="Active", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 0.15, 0.15, 1.0), update=_on_changed,
    )
    static_multi_color: bpy.props.FloatVectorProperty(
        name="Multi", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.0, 0.3, 0.75, 0.9), update=_on_changed,
    )
    static_default_color: bpy.props.FloatVectorProperty(
        name="Default", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.35, 0.65, 1.0, 0.35), update=_on_changed,
    )
    hover_color: bpy.props.FloatVectorProperty(
        name="Hover", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 0.55, 0.0, 1.0), update=_on_changed,
    )
    static_wedge_width: bpy.props.FloatProperty(
        name="Wedge Width",
        description="Half-width of the bone wedge at the head end (pixels)",
        min=1.0, max=30.0, default=5.0, step=10,
        update=_on_changed,
    )
    static_line_width: bpy.props.IntProperty(
        name="Line Width",
        description="Thickness of the wedge outline (pixels)",
        min=1, max=10, default=1,
        update=_on_changed,
    )
    hover_line_width: bpy.props.IntProperty(
        name="Hover Extra Width",
        description="Extra line width added on top of Line Width when hovering over a bone",
        min=0, max=10, default=2,
        update=_on_changed,
    )
    hold_line_width: bpy.props.IntProperty(
        name="Hold Extra Width",
        description="Extra line width added on top of Hover Extra Width while holding the bone picker button",
        min=0, max=10, default=3,
        update=_on_changed,
    )
    overall_size: bpy.props.FloatProperty(
        name="Overall Size",
        description="Global size multiplier applied to the whole bone shape",
        min=0.1, max=5.0, default=1.0, step=10,
        update=_on_changed,
    )
    pivot_ratio: bpy.props.FloatProperty(
        name="Pivot Ratio",
        description="Where the widest point of the bone diamond sits (0=head, 1=tail)",
        min=0.05, max=0.95, default=0.333, step=1, precision=3,
        update=_on_changed,
    )
    fill_opacity: bpy.props.FloatProperty(
        name="Fill Opacity",
        description="Transparency of the bone body fill",
        min=0.0, max=1.0, default=0.25, step=1,
        update=_on_changed,
    )
    head_circle_size: bpy.props.FloatProperty(
        name="Head Circle Size",
        description="Head joint circle radius as a fraction of Wedge Width",
        min=0.1, max=2.0, default=0.55, step=1,
        update=_on_changed,
    )
    tail_circle_size: bpy.props.FloatProperty(
        name="Tail Circle Size",
        description="Tail joint circle radius as a fraction of Wedge Width",
        min=0.1, max=2.0, default=0.36, step=1,
        update=_on_changed,
    )


# ==============================================================================
# BonePickerFeature — UnifiedFeatureExtension
# ==============================================================================

class BonePickerFeature(UnifiedFeatureExtension):
    """Unified extension for the Bone Picker domain."""

    # ── Configuration (class attributes) ──────────────────────────────────

    domain_id = "bone_picker"
    actions = ["start_bone_picker", "stop_bone_picker", "clear_multi_selection"]
    section_title = "Bone Picker"
    draw_tab = "PREFERENCE"
    json_path = ("customize", "bone_picker")
    defaults_path = _DEFAULTS_PATH

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        try:
            if action == "start_bone_picker":
                pass
            elif action == "stop_bone_picker":
                pass
            elif action == "clear_multi_selection":
                obj = core_facade.get_obj()
                storage = getattr(obj, "superskin_storage", None)
                if storage:
                    storage.selected_names = ""
                    storage.selection_history = ""
                    storage.last_clicked_index = -1
                core_facade.show_toast("CLEAN ALL MULTI SELECTION", 1.0)
            else:
                return {"status": "CANCELLED", "message": f"Unknown action: {action}"}
        except Exception as e:
            return {"status": "CANCELLED", "message": str(e)}
        return {"status": "FINISHED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Draw the full Bone Picker section with color and shape controls."""
        bp = context.window_manager.superskin_bone_picker_prefs
        layout.use_property_decorate = False

        layout.label(text="Static Skeleton Overlay", icon='ARMATURE_DATA')

        row = layout.row(align=True)
        for attr, label in (
            ("static_active_color",  "Active"),
            ("static_multi_color",   "Multi"),
            ("static_default_color", "Default"),
            ("hover_color",          "Hover"),
        ):
            sub = row.column(align=True)
            sub.label(text=label)
            sub.prop(bp, attr, text="")

        col = layout.column(align=True)
        col.prop(bp, "static_wedge_width", slider=True)
        col.prop(bp, "static_line_width",  slider=True)
        col.prop(bp, "hover_line_width",   slider=True)
        col.prop(bp, "hold_line_width",    slider=True)

        layout.label(text="Shape", icon='SHAPEKEY_DATA')
        col = layout.column(align=True)
        col.prop(bp, "overall_size",     slider=True)
        col.prop(bp, "pivot_ratio",      slider=True)
        col.prop(bp, "fill_opacity",     slider=True)
        col.prop(bp, "head_circle_size", slider=True)

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """Write section data dict into the live WindowManager property."""
        bp = bpy.context.window_manager.superskin_bone_picker_prefs
        if "static_active_color"  in data: bp.static_active_color  = tuple(data["static_active_color"])
        if "static_multi_color"   in data: bp.static_multi_color   = tuple(data["static_multi_color"])
        if "static_default_color" in data: bp.static_default_color = tuple(data["static_default_color"])
        if "hover_color"          in data: bp.hover_color          = tuple(data["hover_color"])
        if "static_wedge_width"   in data: bp.static_wedge_width   = float(data["static_wedge_width"])
        if "static_line_width"    in data: bp.static_line_width    = int(data["static_line_width"])
        if "hover_line_width"     in data: bp.hover_line_width     = int(data["hover_line_width"])
        if "hold_line_width"      in data: bp.hold_line_width      = int(data["hold_line_width"])
        if "overall_size"         in data: bp.overall_size         = float(data["overall_size"])
        if "pivot_ratio"          in data: bp.pivot_ratio          = float(data["pivot_ratio"])
        if "fill_opacity"         in data: bp.fill_opacity         = float(data["fill_opacity"])
        if "head_circle_size"     in data: bp.head_circle_size     = float(data["head_circle_size"])

    def serialize_into(self, full_dict: dict) -> None:
        """Write current values into full_dict at the correct JSON path."""
        bp = bpy.context.window_manager.superskin_bone_picker_prefs
        full_dict.setdefault("customize", {})["bone_picker"] = {
            "static_active_color":  list(bp.static_active_color),
            "static_multi_color":   list(bp.static_multi_color),
            "static_default_color": list(bp.static_default_color),
            "hover_color":          list(bp.hover_color),
            "static_wedge_width":   bp.static_wedge_width,
            "static_line_width":    bp.static_line_width,
            "hover_line_width":     bp.hover_line_width,
            "hold_line_width":      bp.hold_line_width,
            "overall_size":         bp.overall_size,
            "pivot_ratio":          bp.pivot_ratio,
            "fill_opacity":         bp.fill_opacity,
            "head_circle_size":     bp.head_circle_size,
        }


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register PropertyGroup on WindowManager and the extension with UnifiedRegistry."""
    if hasattr(bpy.types, SSPrefBonePicker.__name__):
        bpy.utils.unregister_class(SSPrefBonePicker)
    bpy.utils.register_class(SSPrefBonePicker)
    bpy.types.WindowManager.superskin_bone_picker_prefs = bpy.props.PointerProperty(
        type=SSPrefBonePicker, options={'SKIP_SAVE'},
    )
    UnifiedRegistry.register(BonePickerFeature())


def unregister():
    """Unregister PropertyGroup and the extension."""
    UnifiedRegistry.unregister("bone_picker")
    try:
        del bpy.types.WindowManager.superskin_bone_picker_prefs
    except Exception:
        pass
    bpy.utils.unregister_class(SSPrefBonePicker)
