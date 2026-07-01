"""Composite visible layers onto real Vertex Groups on the mesh.

Bpy-dependent bridge between LayerStorageService's raw storage and the
mesh's actual Vertex Group weights. Every read of layer/mask data goes
through the owning LayerStorageService instance -- never touches mesh
custom properties directly.
"""

from ...core_subsystems.layer_compositor import LayerCompositor


def flatten_visible_layers_to_mesh(storage, obj):
    """Composite every visible layer onto real Vertex Groups on *obj*.

    Standard formula: Result = Base * (1 - Mask) + Layer * Mask
    Delegates pure math to ``layer_manager.compositor.composite_layers``.
    """
    if not obj or obj.type != 'MESH' or not storage.has_layer_system():
        return

    mesh = obj.data
    vg_list = obj.vertex_groups
    num_verts = len(mesh.vertices)

    if num_verts == 0 or len(vg_list) == 0:
        return

    meta = storage.read_meta_list()
    idx_to_name = {vg.index: vg.name for vg in vg_list
                   if not vg.name.startswith("__ssp_")}

    layer_data_map = storage.harvest_layer_data_map()
    mask_data_map = storage.harvest_mask_data_map()

    result = LayerCompositor.composite_layers(meta, layer_data_map, mask_data_map,
                                               idx_to_name, num_verts)

    for vg in vg_list:
        if not vg.name.startswith("__ssp_"):
            vg.remove(range(num_verts))

    name_to_vg = {vg.name: vg for vg in obj.vertex_groups
                  if not vg.name.startswith("__ssp_")}
    for v_idx, bone_weights in result.items():
        for g_name, w in bone_weights.items():
            if g_name in name_to_vg and w > 0.001:
                name_to_vg[g_name].add([v_idx], w, 'REPLACE')
