"""SuperSkinPro N-panel sidebar — mode-split UI (no tab bar).

The panel adapts its content to the current Blender interaction mode:

  OBJECT mode  — collapsible LAYER sections (LayerViewer with entry gate, data_io,
                 weight_transfer).

  EDIT_MESH    — collapsible SKINNING sections (DeformBoneViewer with exit gate,
                 weight_apply, mirror, …).

System settings (ramps, palette, license, debug) are now hosted in the native
Blender Add-on Preferences panel (Edit > Preferences > Add-ons > Super Skin Pro),
rendered by ``draw_system_for_addon_prefs()``.

All preference *data* lives on ``WindowManager.superskin_prefs`` (core) or on
feature-domain PointerProperties. This module only draws; it holds no state.

Feature domains register via ``UnifiedRegistry`` (Unified Component Architecture).
Each ``UnifiedFeatureExtension`` exposes ``draw_section(layout, context)``,
``is_collapsible()``, ``get_section_title()``, and ``get_draw_tab()``.
"""

import bpy

from ..core_subsystems.license_gateway import LicenseGateway


# =========================================================================
#  Primary entry point — called from panel_main.draw()
# =========================================================================

def draw_mode_split_ui(layout, context):
    """Render either the Object-mode or Edit-mode UI based on context.mode."""
    prefs = context.window_manager.superskin_prefs
    if context.mode == 'OBJECT':
        _draw_object_context(layout, context, prefs)
    elif context.mode == 'EDIT_MESH':
        _draw_edit_context(layout, context, prefs)


# =========================================================================
#  State A: Object Mode — collapsible LAYER spec sections
# =========================================================================

def _draw_object_context(layout, context, prefs):
    """Object-mode content."""
    _draw_viewer_spec(layout, context, 'LAYER')
    _draw_tool_specs(layout, context, 'LAYER')


# =========================================================================
#  State B: Edit Mode — collapsible SKINNING spec sections
# =========================================================================

def _draw_edit_context(layout, context, prefs):
    """Edit-mode content: auto-init guard, then spec sections."""
    obj = context.active_object
    if obj and obj.type == 'MESH' and "ss_layers_meta" not in obj.data:
        from .utils import utils as _utils
        if not _utils._auto_init_pending:
            _utils._auto_init_pending = True
            bpy.app.timers.register(_utils._auto_init_layers, first_interval=0.0)
        layout.label(text="Initializing layer system...", icon='SORTTIME')
        return

    _draw_viewer_spec(layout, context, 'SKINNING')
    _draw_tool_specs(layout, context, 'SKINNING')


# =========================================================================
#  Spec-section draw helpers — Unified Component Architecture
# =========================================================================

def _draw_viewer_spec(layout, context, tab_key):
    """Draw the first non-collapsible spec (the list viewer widget) for *tab_key*."""
    from .registry.register_api import UnifiedRegistry

    for ext in UnifiedRegistry.get_by_tab(tab_key):
        if not ext.is_collapsible():
            ext.draw_section(layout, context)
            return


def _draw_tool_specs(layout, context, tab_key):
    """Draw all collapsible tool specs for *tab_key* with separators."""
    from .registry.register_api import UnifiedRegistry

    for ext in UnifiedRegistry.get_by_tab(tab_key):
        if ext.is_collapsible():
            layout.separator(factor=0.4)
            _draw_collapsible_box_ext(layout, context, ext)


# =========================================================================
#  Collapsible section helper
# =========================================================================

def _draw_collapsible_box(layout, ui_state, bool_attr, title, draw_body_fn):
    """Draw a native Blender collapsible section using layout.panel().

    Legacy helper kept for the SYSTEM tab (ramps, palette, license) which is
    not part of the Unified Component Architecture.
    """
    header, body = layout.panel(f"superskin_{bool_attr}", default_closed=True)
    header.label(text=title)
    if body is not None:
        draw_body_fn(body)


def _draw_collapsible_box_ext(layout, context, ext):
    """Draw a collapsible section for a ``UnifiedFeatureExtension``.

    Uses ``layout.panel()`` with a Blender-managed identifier derived from
    ``ext.get_id()`` so expand/collapse state persists across redraws.
    """
    domain_id = ext.get_id()
    panel_id = f"superskin_{domain_id}_section"
    header, body = layout.panel(panel_id, default_closed=not ext.is_expanded_by_default())
    header.label(text=ext.get_section_title())
    if body is not None:
        ext.draw_section(body, context)


# =========================================================================
#  Add-on Preferences entry point
# =========================================================================

def draw_system_for_addon_prefs(layout, context):
    """Draw the System/Customize section inside Blender's Add-on Preferences panel."""
    prefs = context.window_manager.superskin_prefs
    _draw_system(layout, context, prefs)


# =========================================================================
#  System tab — license + visual customization (merged from CUSTOMIZE tab)
# =========================================================================

def _draw_system(layout, context, prefs):
    """SYSTEM tab: visual customization (ramps, palette, feature extensions),
    license activation, system/debug, and about."""
    from .registry.register_api import UnifiedRegistry

    ui_state = prefs.ui_state
    customize = prefs.customize

    layout.use_property_decorate = False

    # Visual Customization — formerly the standalone CUSTOMIZE tab
    _draw_collapsible_box(
        layout, ui_state, "single_ramp_expanded", "Single Mode Color Ramp",
        lambda box: _draw_ramp_body(box, None, customize.single_ramp, "single"),
    )
    layout.separator(factor=0.4)
    _draw_collapsible_box(
        layout, ui_state, "multi_palette_expanded", "Multi Mode Color Palette",
        lambda box: _draw_palette_body(box, customize.multi_palette.colors),
    )
    layout.separator(factor=0.4)
    _draw_collapsible_box(
        layout, ui_state, "mask_ramp_expanded", "Mask / Layer Color Ramp",
        lambda box: _draw_ramp_body(box, None, customize.mask_ramp, "mask"),
    )

    # PREFERENCE-tab extensions from feature domains (e.g. Bone Picker Colors)
    for ext in UnifiedRegistry.get_by_tab('PREFERENCE'):
        layout.separator(factor=0.4)
        _draw_collapsible_box_ext(layout, context, ext)

    layout.separator()

    # License
    _draw_license(layout, prefs)

    layout.separator()

    box = layout.box()
    box.label(text="System / Performance", icon='INFO')
    box.label(text="Coming soon")

    layout.separator()
    box = layout.box()
    box.label(text="Developer / Debug Tools", icon='CONSOLE')
    box.operator("superskin.reset_license_activation", text="Reset All Activate", icon='TRASH')
    box.operator("superskin.reset_prefs", text="Reset to Default", icon='LOOP_BACK')

    layout.separator()
    _draw_placeholder(layout, "About", "Coming soon")


# =========================================================================
#  Ramp / palette draw helpers (moved from _draw_customize)
# =========================================================================

def _draw_ramp_body(box, context, ramp_group, ramp_id):
    stops_coll = ramp_group.stops
    count = len(stops_coll)
    idx   = ramp_group.active_index

    row = box.row()
    row.template_list(
        "SUPERSKIN_UL_ramp_stops", "",
        ramp_group, "stops",
        ramp_group, "active_index",
        rows=4,
    )

    col_btns = row.column(align=True)

    up_row = col_btns.row(align=True)
    up_row.enabled = 0 < idx < count
    up = up_row.operator("superskin.move_ramp_stop", text="", icon='TRIA_UP')
    up.ramp_id, up.index, up.direction = ramp_id, idx, -1

    down_row = col_btns.row(align=True)
    down_row.enabled = 0 <= idx < count - 1
    down = down_row.operator("superskin.move_ramp_stop", text="", icon='TRIA_DOWN')
    down.ramp_id, down.index, down.direction = ramp_id, idx, 1

    rm_row = col_btns.row(align=True)
    rm_row.enabled = count > 2 and 0 <= idx < count
    rm = rm_row.operator("superskin.remove_ramp_stop", text="", icon='X')
    rm.ramp_id, rm.index = ramp_id, idx

    add_row = box.row()
    op = add_row.operator("superskin.add_ramp_stop", text="Add Stop", icon='ADD')
    op.ramp_id = ramp_id


def _draw_palette_body(box, colors_coll):
    row = box.row(align=True)
    for item in colors_coll:
        row.prop(item, "color", text="")


# =========================================================================
#  License section helper
# =========================================================================

def _draw_license(layout, prefs):
    lic = prefs.license
    box = layout.box()

    limit = LicenseGateway.layer_limit()
    if limit is None:
        box.label(text="Status: Pro Activated", icon='CHECKMARK')
    else:
        box.label(text=f"Status: Free (max {limit} layers)", icon='INFO')

    box.prop(lic, "license_key", text="License Key")
    box.operator("superskin.activate_license", text="Activate", icon='UNLOCKED')

    if lic.status_message:
        box.label(text=lic.status_message)


def _draw_placeholder(layout, title, subtitle):
    box = layout.box()
    box.label(text=title, icon='INFO')
    box.label(text=subtitle)
