"""Shared layout helper — list + search + side-button column.

``draw_list_with_sidebar`` replaces the hand-rolled ``template_list`` +
search-row + side-button code that was duplicated in both
``widget_deform_bones.py`` and ``widget_tools.py``.
"""


def draw_list_with_sidebar(layout, context, *,
                           ui_list_idname: str,
                           data,
                           collection_prop: str,
                           active_data,
                           active_prop: str,
                           search_owner=None,
                           search_prop: str = None,
                           rows: int = 8,
                           button_defs=(),
                           after_list_fn=None):
    """Draw a ``template_list`` with an optional search box and side buttons.

    The list + search occupy the left column and the side buttons occupy
    a narrower right column — matching the existing bones and layers
    layouts.

    Args:
        layout: The Blender ``UILayout`` to draw into.
        context: ``bpy.context``.
        ui_list_idname: Registered UIList class name (e.g.
            ``"MESH_UL_influence_list_view"``).
        data: Data-block owning the collection property.
        collection_prop: Name of the collection property on *data*.
        active_data: Data-block owning the active-index property.
        active_prop: Name of the active-index property on *active_data*.
        search_owner: Data-block owning the search property (if *None*, no
            search row is drawn).
        search_prop: Name of the search StringProperty on *search_owner*.
        rows: Number of visible rows in the list (default 8).
        after_list_fn: Optional ``(col_list) -> None`` callback, invoked
            immediately after ``template_list`` (before the search row), in
            the same left-hand column, flush against the list with no gap.
            Lets a caller append extra rows that visually attach to the
            list (e.g. synthetic rows for entries that aren't part of the
            backing RNA collection at all, so can't go through
            ``template_list`` itself).
        button_defs: Iterable of button definitions for the side column.
            Each entry is one of:

            * ``("operator", op_idname, icon, text, extra_props_dict)``
            * ``("toggle", owner, prop_name, icon)``
            * ``("enum_radio", owner, prop_name, enum_value, icon)``
            * ``("menu", menu_idname, icon, text)``
            * ``("separator", factor)``

            For ``"operator"`` and ``"toggle"``, *icon* may be a callable
            (``(context) -> str``) for dynamic icon selection.

            ``"enum_radio"`` draws one button per call bound to a single
            ``EnumProperty`` via ``prop_enum`` — Blender depresses exactly
            one button at a time (whichever matches the property's current
            value), giving mutually-exclusive choice-button behaviour for
            free, with no manual exclusivity bookkeeping needed. Pass one
            entry per enum item to build the full radio group.
    """
    row = layout.row(align=False)

    # ── Left column: list + search ────────────────────────────────────
    col_list = row.column(align=False)
    col_list.scale_y = 1
    col_list.template_list(
        ui_list_idname, "",
        data, collection_prop,
        active_data, active_prop,
        rows=rows,
        # maxrows == rows disables Blender's native per-list resize grip
        # (it only renders when maxrows != rows) — resizing is driven
        # entirely by the shared drag handle in widget_tools.py instead.
        maxrows=rows,
    )

    # Drawn before the search row so it sits flush against the real list
    # rows, with no search-bar gap visually separating the two groups.
    if after_list_fn is not None:
        after_list_fn(col_list)

    if search_prop and search_owner is not None:
        row_search = col_list.row(align=True)
        row_search.scale_y = 0.95
        row_search.prop(search_owner, search_prop, text="", icon='VIEWZOOM')

    # ── Right column: side buttons ────────────────────────────────────
    if button_defs:
        col_btns = row.column(align=True)
        col_btns.scale_y = 1
        col_btns.ui_units_x = 1

        for entry in button_defs:
            kind = entry[0]

            if kind == "operator":
                _, op_idname, icon, text, extra_props = entry
                icon_str = icon(context) if callable(icon) else icon
                op = col_btns.operator(op_idname, text=text, icon=icon_str)
                for prop_name, prop_value in extra_props.items():
                    setattr(op, prop_name, prop_value)

            elif kind == "toggle":
                _, owner, prop_name, icon = entry
                icon_str = icon(context) if callable(icon) else icon
                col_btns.prop(owner, prop_name, text="", icon=icon_str, toggle=True)

            elif kind == "enum_radio":
                _, owner, prop_name, enum_value, icon = entry
                icon_str = icon(context) if callable(icon) else icon
                col_btns.prop_enum(owner, prop_name, enum_value, text="", icon=icon_str)

            elif kind == "menu":
                _, menu_idname, icon, text = entry
                col_btns.menu(menu_idname, text=text, icon=icon)

            elif kind == "separator":
                _, factor = entry
                col_btns.separator(factor=factor)

            else:
                raise ValueError(f"Unknown button_def kind: {kind!r}")
