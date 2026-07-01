"""Property update callbacks for SuperSkinPro PropertyGroups.

These functions are registered as `update=` callbacks on bpy.props
declarations.  They're kept in a separate module so the core data-
model definitions stay focused on structure.
"""


def on_skin_sub_tabs_update(self, context):
    """Switch shader visualizer when the Skin sub-tab changes.

    BONES → SINGLE or MULTI (user-toggleable via shortcut).
    LAYERS → MASK (forced, black-and-white ramp).
    """
    try:
        from ..core.facade import CoreFacade
        facade = CoreFacade(context)
        facade.apply_active_bone()
    except Exception:
        pass
    
    # Force redraw across all VIEW_3D areas
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()