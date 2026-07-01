import bpy


def draw_section(layout):
    col = layout.column(align=True)
    col.scale_y = 1.2
    col.operator(
        "object.mw_copy_skin_weight_maya",
        text="Transfer Weight to Selected Mesh",
    )
