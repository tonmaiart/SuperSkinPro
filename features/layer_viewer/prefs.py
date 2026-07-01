"""LayerViewer preferences — registers the layer list section under the LAYER tab.

This domain has no persistent user settings; the PrefsExtensionSpec is used
solely to anchor the layer list draw function at the top of the LAYER tab
with ``collapsible=True`` so it renders with a collapsible wrapper containing
the layer list and the entry-gate operator.
"""

import os
import bpy

from ...registry.prefs_extension_registry import PrefsExtensionRegistry, PrefsExtensionSpec
from . import ui


def draw_section(layout):
    """Render the Layer List and entry-gate operator inside a box container."""
    box = layout.box()
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        box.label(text="No mesh active", icon='ERROR')
        return
    if "ss_layers_meta" not in obj.data:
        box.label(text="Enter Edit Mode to initialize layers", icon='INFO')
        return
    ui.draw_layer_list(box, bpy.context, rows=8)
    box.separator(factor=0.4)
    row = box.row()
    row.scale_y = 1.4
    row.operator("superskin.enter_layer_edit", icon='EDITMODE_HLT')


def populate(data: dict) -> None:
    pass


def serialize_into(full_dict: dict) -> None:
    pass


def register() -> None:
    PrefsExtensionRegistry.register(PrefsExtensionSpec(
        json_key="layer_viewer",
        json_path=("layer_viewer",),
        section_title="Layers Management",
        draw_tab="LAYER",
        draw_section_fn=draw_section,
        populate_fn=populate,
        serialize_into_fn=serialize_into,
        defaults_path=os.path.join(os.path.dirname(__file__), "default_config.json"),
        collapsible=True,
    ))


def unregister() -> None:
    PrefsExtensionRegistry.unregister("layer_viewer")
