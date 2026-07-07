"""SuperSkinPro N-panel sidebar — interface-split UI (no tab bar).

The panel adapts its content to ``WindowManager.superskin_active_interface``
(owned by ``panel_main.py``), NOT to the current Blender interaction mode:

  LAYER    — collapsible LAYER sections (LayerViewer with entry gate,
             weight_transfer — which also owns Export/Import JSON).

  SKINNING — collapsible SKINNING sections (DeformBoneViewer with exit gate,
             weight_apply, mirror, …).

This state is deliberately decoupled from ``context.mode`` — see
``features/controller/ops_scene_modes.py`` for the three points where it
flips (Edit Layer Weight, Save Weights, and the auto-save guard's
unguarded-Tab-exit detection).

System settings (ramps, palette, license) plus PREFERENCE-tab feature
extensions (including the ``debug_console`` domain, which now owns the
per-category debug log toggles) are hosted in the "Preference" sidebar panel
(``panel_gate.py``), rendered by ``draw_preferences_body()``.

All preference *data* lives on ``WindowManager.superskin_prefs`` (core) or on
feature-domain PointerProperties. This module only draws; it holds no state.

Feature domains register via ``UnifiedRegistry`` (Unified Component Architecture).
Each ``UnifiedFeatureExtension`` exposes ``draw_section(layout, context)``,
``is_collapsible()``, ``get_section_title()``, and ``get_draw_tabs()``.
"""

import bpy


# =========================================================================
#  Primary entry point — called from panel_main.draw()
# =========================================================================

def draw_mode_split_ui(layout, context):
    """Render either the Layer or Skinning interface based on
    ``context.window_manager.superskin_active_interface`` (not context.mode)."""
    prefs = context.window_manager.superskin_prefs
    active = context.window_manager.superskin_active_interface
    if active == 'LAYER':
        _draw_layer_interface(layout, context, prefs)
    elif active == 'SKINNING':
        _draw_skinning_interface(layout, context, prefs)


# =========================================================================
#  State A: Layer interface — collapsible LAYER spec sections
# =========================================================================

def _draw_layer_interface(layout, context, prefs):
    """Layer-interface content."""
    _draw_viewer_spec(layout, context, 'LAYER')
    _draw_tool_specs(layout, context, 'LAYER')


# =========================================================================
#  State B: Skinning interface — collapsible SKINNING spec sections
# =========================================================================

def _draw_skinning_interface(layout, context, prefs):
    """Skinning-interface content: auto-init guard, then spec sections."""
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
            layout.separator(factor=0.2)
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
#  Preference panel entry point (interface/panel_gate.py)
# =========================================================================

def draw_preferences_body(layout, context):
    """Draw the System/Customize section inside the sidebar "Preference" panel.

    Formerly hosted in Blender's native Add-on Preferences window; moved here
    so users don't have to leave the viewport to reach these settings.
    """
    prefs = context.window_manager.superskin_prefs
    _draw_preferences(layout, context, prefs)


# =========================================================================
#  Preference body — visual customization + feature extensions + system/debug
# =========================================================================

def _draw_preferences(layout, context, prefs):
    """Preference panel body: visual customization (ramps, palette, feature
    extensions), system actions, and about. Per-category debug log toggles
    and the live log view now live in the ``debug_console`` feature
    extension, drawn as part of the PREFERENCE-tab extensions loop below,
    not hardcoded here.

    License activation is intentionally NOT drawn here — the "Preference"
    panel that hosts this body already shows license entry/status at its own
    top level (see ``panel_gate.py``), so repeating it here would be
    circular.
    """
    from .registry.register_api import UnifiedRegistry

    ui_state = prefs.ui_state
    customize = prefs.customize

    layout.use_property_decorate = False

    # `debug_console` pinned above the hardcoded ramp/palette sections.
    # UnifiedFeatureExtension.priority only sorts extensions *within* a tab's
    # own loop (see UnifiedRegistry.get_by_tab()) -- there is no generic hook
    # for an extension to ask to be drawn before this function's hardcoded
    # content, so this is a deliberate, explicit special case rather than a
    # reusable mechanism. Excluded from the extensions loop below to avoid a
    # duplicate draw.
    debug_console_ext = UnifiedRegistry.get_by_id("debug_console")
    if debug_console_ext is not None:
        _draw_collapsible_box_ext(layout, context, debug_console_ext)
        layout.separator(factor=0.2)

    # Visual Customization — formerly the standalone CUSTOMIZE tab
    _draw_collapsible_box(
        layout, ui_state, "single_ramp_expanded", "Single Mode Color Ramp",
        lambda box: _draw_ramp_body(box, None, customize.single_ramp, "single"),
    )
    layout.separator(factor=0.2)
    _draw_collapsible_box(
        layout, ui_state, "multi_palette_expanded", "Multi Mode Color Palette",
        lambda box: _draw_palette_body(box, customize.multi_palette.colors),
    )
    layout.separator(factor=0.2)
    _draw_collapsible_box(
        layout, ui_state, "mask_ramp_expanded", "Mask / Layer Color Ramp",
        lambda box: _draw_ramp_body(box, None, customize.mask_ramp, "mask"),
    )

    # PREFERENCE-tab extensions from feature domains (e.g. Bone Picker Colors)
    # `debug_console` is pinned above and excluded here to avoid a double draw.
    for ext in UnifiedRegistry.get_by_tab('PREFERENCE'):
        if ext.get_id() == "debug_console":
            continue
        layout.separator(factor=0.2)
        _draw_collapsible_box_ext(layout, context, ext)

    layout.separator(factor=0.4)

    box = layout.box()
    box.label(text="System / Performance", icon='INFO')
    box.label(text="Coming soon")

    layout.separator(factor=0.4)
    box = layout.box()
    box.label(text="System Actions", icon='TOOL_SETTINGS')
    box.operator("superskin.reset_license_activation", text="Reset All Activate", icon='TRASH')
    box.operator("superskin.reset_prefs", text="Reset to Default", icon='LOOP_BACK')

    layout.separator(factor=0.4)
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


def _draw_placeholder(layout, title, subtitle):
    box = layout.box()
    box.label(text=title, icon='INFO')
    box.label(text=subtitle)
