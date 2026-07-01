"""MirrorFeature — Unified Component Architecture implementation for the mirror domain.

Collapses the old MirrorDomain (action dispatch) and prefs.py (PropertyGroup,
draw, persistence) into a single UnifiedFeatureExtension subclass.

Owns:
  - SSPrefMirror / SSPrefMirrorSRItem PropertyGroups (registered on WindowManager)
  - MirrorPreferencesService (stateless accessor)
  - Action dispatch: "mirror"
  - UI layout: draw_section()
  - JSON persistence: populate() / serialize_into()
"""

import bpy
import os

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade
from .logic import execute_mirror_pipeline

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


# ==============================================================================
# Property Groups
# ==============================================================================

def _on_changed(self, context):
    from ...core.facade import CoreFacade
    CoreFacade.save_prefs()


class SSPrefMirrorSRItem(bpy.types.PropertyGroup):
    """A single bone-name search/replace rule used to find mirror pairs."""
    search_text:  bpy.props.StringProperty(name="Search",  update=_on_changed)
    replace_text: bpy.props.StringProperty(name="Replace", update=_on_changed)


class SSPrefMirror(bpy.types.PropertyGroup):
    """Mirror settings (per-machine — shared across every .blend file)."""
    mirror_axis: bpy.props.EnumProperty(
        name="MirrorAxis",
        items=[
            ('X', "X", "Mirror along axis X"),
            ('Y', "Y", "Mirror along axis Y"),
            ('Z', "Z", "Mirror along axis Z"),
        ],
        default='X',
        update=_on_changed,
    )
    direction: bpy.props.EnumProperty(
        name="Direction",
        items=[
            ('POS_NEG', "Positive to Negative", "Mirror from positive side to negative side"),
            ('NEG_POS', "Negative to Positive", "Mirror from negative side to positive side"),
        ],
        default='POS_NEG',
        update=_on_changed,
    )
    both_data: bpy.props.BoolProperty(
        name="Mirror both layer and bone data",
        description="This will mirror both layer and bone data at once.",
        default=True,
        update=_on_changed,
    )
    search_replace_pairs:  bpy.props.CollectionProperty(type=SSPrefMirrorSRItem)
    search_replace_index:  bpy.props.IntProperty(name="Index", default=0)


# ==============================================================================
# Preferences accessor (replaces MirrorPreferencesService)
# ==============================================================================

class MirrorPreferencesService:
    """Stateless accessor for mirror prefs — consumed by logic.py."""

    @staticmethod
    def _prefs() -> "SSPrefMirror":
        return bpy.context.window_manager.superskin_mirror_prefs

    @classmethod
    def get_mirror_axis(cls) -> str:
        return cls._prefs().mirror_axis

    @classmethod
    def get_mirror_direction(cls) -> str:
        return cls._prefs().direction

    @classmethod
    def get_mirror_both_data(cls) -> bool:
        return cls._prefs().both_data

    @classmethod
    def get_mirror_search_replace_pairs(cls) -> list:
        return [(p.search_text, p.replace_text) for p in cls._prefs().search_replace_pairs]


# ==============================================================================
# MirrorFeature — UnifiedFeatureExtension
# ==============================================================================

class MirrorFeature(UnifiedFeatureExtension):
    """Unified extension for the Mirror domain."""

    # ── Configuration (class attributes) ───────────────────────────────────

    domain_id = "mirror"
    actions = ["mirror"]
    section_title = "Mirror"
    draw_tab = "SKINNING"
    defaults_path = _DEFAULTS_PATH

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        try:
            execute_mirror_pipeline(core_facade)
        except ValueError as e:
            return {"status": "CANCELLED", "message": str(e)}
        return {"status": "FINISHED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Draw the full Mirror section: direction, axis, S/R pairs list, operator."""
        mirror = context.window_manager.superskin_mirror_prefs

        col_opts = layout.column(align=True)
        row_dir = col_opts.split(factor=0.3, align=True)
        row_dir.label(text="Direction:")
        row_dir.prop(mirror, "direction", text="")
        col_opts.separator(factor=0.5)
        row_axis = col_opts.split(factor=0.3, align=True)
        row_axis.label(text="Mirror Axis:")
        row_axis.prop(mirror, "mirror_axis", text="")
        layout.prop(mirror, "both_data", toggle=False)
        layout.label(text="Mapping Keywords:")
        self._draw_sr_body(layout.box(), context, mirror)
        row_btn = layout.row()
        row_btn.scale_y = 1.5
        row_btn.operator("object.mirror_weights", text="Mirror Weights", icon='MOD_MIRROR')

    def _draw_sr_body(self, box, context, mirror) -> None:
        sr_coll = mirror.search_replace_pairs
        idx = mirror.search_replace_index

        row = box.row()
        row.template_list(
            "SUPERSKIN_UL_mirror_sr", "",
            mirror, "search_replace_pairs",
            mirror, "search_replace_index",
            rows=4,
        )

        col_btns = row.column(align=True)
        mapping_column = col_btns.column(align=True)
        mapping_column.operator("superskin.add_mirror_sr", text="", icon='ADD')
        mapping_column.enabled = 0 <= idx < len(sr_coll)
        rm = mapping_column.operator("superskin.remove_mirror_sr", text="", icon='REMOVE')
        rm.index = idx

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """Write section data dict into the live WindowManager property."""
        mirror = bpy.context.window_manager.superskin_mirror_prefs
        mirror.mirror_axis = data.get("mirror_axis", "X")
        mirror.direction   = data.get("direction",   "POS_NEG")
        mirror.both_data   = data.get("both_data",   True)

        sr_coll = mirror.search_replace_pairs
        sr_coll.clear()
        for pair in data.get("search_replace_pairs", []):
            item = sr_coll.add()
            item.search_text  = pair[0]
            item.replace_text = pair[1]

    def serialize_into(self, full_dict: dict) -> None:
        """Write current values into full_dict at the correct JSON path."""
        mirror = bpy.context.window_manager.superskin_mirror_prefs
        full_dict["mirror"] = {
            "mirror_axis": mirror.mirror_axis,
            "direction":   mirror.direction,
            "both_data":   mirror.both_data,
            "search_replace_pairs": [
                [p.search_text, p.replace_text]
                for p in mirror.search_replace_pairs
            ],
        }


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register PropertyGroups on WindowManager and the extension with UnifiedRegistry."""
    bpy.utils.register_class(SSPrefMirrorSRItem)
    bpy.utils.register_class(SSPrefMirror)
    bpy.types.WindowManager.superskin_mirror_prefs = bpy.props.PointerProperty(
        type=SSPrefMirror, options={'SKIP_SAVE'},
    )
    UnifiedRegistry.register(MirrorFeature())


def unregister():
    """Unregister PropertyGroups and the extension."""
    UnifiedRegistry.unregister("mirror")
    try:
        del bpy.types.WindowManager.superskin_mirror_prefs
    except Exception:
        pass
    bpy.utils.unregister_class(SSPrefMirror)
    bpy.utils.unregister_class(SSPrefMirrorSRItem)



