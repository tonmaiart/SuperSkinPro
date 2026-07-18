"""Shared ColorRamp read/write helpers for the vgcolor domain.

Both ``vgcolor_feature.py`` (settings UI + JSON persistence) and
``native_sync.py`` (pushing the active ramp into Blender's native
``weight_color_range``, and restoring it afterward) need the same "read
stops out of a ColorRamp" / "rebuild a ColorRamp from stops" logic, plus a
way to get at this domain's own two persistent ColorRamps -- kept here once
so neither drifts out of sync with the other.
"""

import bpy

_RAMP_TEXTURE_NAMES = {
    "edit": ".SSP_VGColor_EditRamp",
    "mask": ".SSP_VGColor_MaskRamp",
}


def get_or_create_ramp_texture(ramp_id: str) -> "bpy.types.Texture | None":
    """Return this domain's own hidden Texture datablock backing *ramp_id*'s
    ColorRamp (``"edit"`` or ``"mask"``), creating it (get-or-create by
    name, safe across F3 reloads / repeated calls) if it doesn't exist yet.

    A Texture is the standard, well-established Blender-addon trick for
    owning a real, native ``ColorRamp`` -- ``layout.template_color_ramp()``
    (the native gradient-bar-with-drag-handles widget the user asked for)
    only works on an actual ``bpy.types.ColorRamp``-typed property, which
    only exists on a handful of built-in ID types (Texture, shader nodes,
    FCurve modifiers...) -- there is no way to get that exact widget on a
    custom PropertyGroup. The leading-dot name marks it as
    SuperSkinPro-internal (the same convention Blender itself uses for
    internal-only datablocks), keeping it out of normal texture
    browsers/pickers. ``use_fake_user=True`` protects it from orphan-data
    purges, since nothing ever references it through a material/object.

    This texture is deliberately NOT the persistence source of truth --
    ``default_config.json`` / ``user.json`` are, same as every other
    domain. It's only a live editing surface: ``VGColorFeature.populate()``
    rebuilds its ``color_ramp`` from JSON on every load, and a periodic
    watcher (see ``vgcolor_feature.py``) detects live drag-edits and saves
    them back out, since native ``ColorRampElement`` properties have no
    addon-attachable ``update=`` callback the way a custom PropertyGroup's
    would.

    Returns ``None`` (never raises) if ``bpy.data`` is currently
    inaccessible -- Blender wraps it in a ``_RestrictData`` proxy during
    early addon/extension registration at startup, before the first
    ``load_post`` handler has run, and any ``bpy.data.textures`` access
    during that window raises ``AttributeError``. Every call site in this
    domain treats a ``None`` return as "not ready yet, try again on the
    next call" rather than a fatal error -- the texture always ends up
    created moments later, the first time the panel actually draws or
    ``populate()`` runs from ``load_post``.
    """
    name = _RAMP_TEXTURE_NAMES[ramp_id]
    try:
        tex = bpy.data.textures.get(name)
        if tex is None:
            tex = bpy.data.textures.new(name, type='BLEND')
            tex.use_fake_user = True
            tex.use_color_ramp = True
        return tex
    except AttributeError:
        return None


def remove_ramp_textures() -> None:
    """Remove both ramp textures from bpy.data — called from unregister()."""
    try:
        for name in _RAMP_TEXTURE_NAMES.values():
            tex = bpy.data.textures.get(name)
            if tex is not None:
                bpy.data.textures.remove(tex)
    except Exception:
        pass


def read_stops(ramp) -> list:
    """Return a ColorRamp's elements as ``[(position, (r, g, b)), ...]``, sorted."""
    stops = [(el.position, (el.color[0], el.color[1], el.color[2])) for el in ramp.elements]
    stops.sort(key=lambda t: t[0])
    return stops


def write_stops(ramp, stops: list) -> None:
    """Rebuild *ramp*'s elements to match *stops* (list of (pos, rgb-or-rgba)).

    Standard safe pattern for scripting a ColorRamp: trim down to exactly
    one element first (a ColorRamp can never have zero), set it to the
    first stop, then ``.new(pos)`` for every remaining stop -- ``.new()``
    inserts already position-sorted, avoiding the reordering hazards of
    mutating ``.position`` on pre-existing elements in an arbitrary order.
    """
    if not stops:
        return
    stops = sorted(stops, key=lambda t: t[0])
    elements = ramp.elements
    while len(elements) > 1:
        elements.remove(elements[-1])

    def _rgba(c):
        return (c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0)

    pos0, color0 = stops[0]
    elements[0].position = pos0
    elements[0].color = _rgba(color0)
    for pos, color in stops[1:]:
        el = elements.new(pos)
        el.color = _rgba(color)
