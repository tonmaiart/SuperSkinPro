import bpy


def draw_section(layout, context):
    prefs = context.window_manager.superskin_weight_transfer_prefs

    col = layout.column(align=True)

    row = col.split(factor=0.4, align=True)
    row.label(text="Layer Output:")
    row.prop(prefs, "layer_output", text="")

    row = col.split(factor=0.4, align=True)
    row.label(text="Insert Method:")
    row.prop(prefs, "insert_method", text="")

    row = col.split(factor=0.4, align=True)
    row.label(text="Transfer Method:")
    row.prop(prefs, "transfer_method", text="")

    layout.separator(factor=0.8)

    btn_col = layout.column(align=True)
    btn_col.scale_y = 1.2
    btn_col.operator(
        "object.mw_copy_skin_weight_maya",
        text="Transfer Weight to Selected Mesh",
    )

    layout.separator(factor=0.8)

    layout.prop(prefs, "auto_assign_armature", toggle=False)

    io_row = layout.row(align=True)
    io_row.scale_y = 1.2
    io_row.operator("superskin.export_weight_json", text="Export JSON", icon='EXPORT')
    io_row.operator("superskin.import_weight_json", text="Import JSON", icon='IMPORT')
