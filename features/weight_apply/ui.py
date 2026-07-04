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
    _draw_smooth_row(col, p)
    col.separator(factor=0.6)
    _draw_op_row(col, "object.mw_sharpen_weight", "Sharpen", p, "sharpen_val",
                 "SUPERSKIN_MT_sharpen_presets")


def _draw_op_row(col, op_idname, label, p, val_prop, menu_id):
    split = col.split(factor=0.3, align=False)
    split.scale_y = 2.2
    split.operator(op_idname, text=label)
    right = split.column(align=True)
    row = right.row(align=True)
    row.scale_y = 0.75
    row.prop(p, val_prop, text="", slider=True)
    row.menu(menu_id, text="", icon='PRESET')


def _draw_smooth_row(col, p):
    split = col.split(factor=0.3, align=False)
    split.scale_y = 2.2
    split.operator("object.mw_smooth_weight", text="Smooth")
    right = split.column(align=True)
    row = right.row(align=True)
    row.scale_y = 0.75
    row.prop(p, "smooth_val", text="", slider=True)
    row.menu("SUPERSKIN_MT_smooth_presets", text="", icon='PRESET')
    opts = right.column(align=True)
    opts.scale_y = 0.55
    opts.prop(p, "smooth_affected_only", text="Smooth Affected Only", toggle=False)
    opts.prop(p, "smooth_across_surface", text="Smooth Across Surface", toggle=False)
