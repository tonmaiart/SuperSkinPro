"""Weight Apply — draws Add/Scale/Smooth/Sharpen section."""


def draw_section(layout):
    from .weight_apply_feature import get_prefs
    p = get_prefs()

    col = layout.column(align=True)

    _draw_op_row(col, "object.mw_add_weight", "Add", p, "add_val",
                 "SUPERSKIN_MT_add_presets")
    col.separator(factor=0.6)
    _draw_op_row(col, "object.mw_scale_weight", "Scale", p, "scale_val",
                 "SUPERSKIN_MT_scale_presets")
    col.separator(factor=0.6)
    _draw_op_row(col, "object.mw_smooth_weight", "Smooth", p, "smooth_val",
                 "SUPERSKIN_MT_smooth_presets")
    col.separator(factor=0.6)
    _draw_op_row(col, "object.mw_sharpen_weight", "Sharpen", p, "sharpen_val",
                 "SUPERSKIN_MT_sharpen_presets")

    col.separator(factor=1.0)
    opts = col.column(align=True)
    opts.prop(p, "smooth_affected_only", text="Smooth Affected Only", toggle=False)
    opts.prop(p, "smooth_across_surface", text="Smooth Across Surface", toggle=False)


def _draw_op_row(col, op_idname, label, p, val_prop, menu_id):
    split = col.split(factor=0.25, align=True)
    split.operator(op_idname, text=label)
    right = split.row(align=True)
    right.prop(p, val_prop, text="", slider=True)
    right.menu(menu_id, text="", icon='PRESET')
