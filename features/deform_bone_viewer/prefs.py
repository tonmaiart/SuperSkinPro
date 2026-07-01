"""DeformBoneViewer preferences — registers the deform bone list section
under the SKINNING tab as the first (top-priority) entry.

This domain has no persistent user settings; the PrefsExtensionSpec is used
solely to anchor the bone list draw function at the top of the SKINNING tab
with ``collapsible=True`` so it renders with a collapsible wrapper containing
the bone list and the save/exit operator.
"""

import os
import bpy

from ...registry.prefs_extension_registry import PrefsExtensionRegistry, PrefsExtensionSpec
from . import ui


def draw_section(layout):
    """Render the Deform Bone List and save/exit operator inside a box container."""
    box = layout.box()
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        box.label(text="No mesh active", icon='ERROR')
        return
    ui.draw_influence_list_system(box, bpy.context, rows=8)
    box.separator(factor=0.4)
    row = box.row()
    row.scale_y = 1.4
    row.operator("superskin.save_weight_and_exit", icon='IMPORT')


def populate(data: dict) -> None:
    pass


def serialize_into(full_dict: dict) -> None:
    pass


def register() -> None:
    PrefsExtensionRegistry.register(PrefsExtensionSpec(
        json_key="deform_bone_viewer",
        json_path=("deform_bone_viewer",),
        section_title="Deform Bones List",
        draw_tab="SKINNING",
        draw_section_fn=draw_section,
        populate_fn=populate,
        serialize_into_fn=serialize_into,
        defaults_path=os.path.join(os.path.dirname(__file__), "default_config.json"),
        collapsible=True,
    ))


def unregister() -> None:
    PrefsExtensionRegistry.unregister("deform_bone_viewer")
