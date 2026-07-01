"""Auto-heal layer & mask storage after mesh topology changes.

Interpolates weights/masks for vertices created by topology edits (loop
cuts, extrude, subdivide, etc.) and prunes entries for deleted vertices.
Delegates pure healing to LayerCompositor.
"""

from ...core_subsystems.layer_compositor import LayerCompositor


def heal_new_vertices_storage(storage, obj):
    if not obj or obj.type != 'MESH' or not storage.has_layer_system():
        return False

    mesh = obj.data
    num_verts = len(mesh.vertices)
    if num_verts == 0:
        return False

    neighbours = storage.build_mesh_neighbors()
    meta = storage.read_meta_list()
    healed = False

    for layer in meta:
        l_idx = layer["index"]

        raw_layer = storage.read_layer_raw(l_idx)
        if raw_layer:
            layer_dict = LayerCompositor.decode(raw_layer)
            if layer_dict:
                layer_dict, mod = LayerCompositor.heal_layer_dict(layer_dict, neighbours, num_verts)
                if mod:
                    storage.write_layer_dict(l_idx, layer_dict)
                    healed = True

        raw_mask = storage.read_mask_raw(l_idx)
        mask_default = float(layer.get("mask_default", 1.0))
        if raw_mask:
            mask_dict = LayerCompositor.decode(raw_mask)
            if mask_dict:
                mask_dict, mod = LayerCompositor.heal_mask_dict(mask_dict, neighbours, num_verts, mask_default)
                if mod:
                    storage.write_mask_dict(l_idx, mask_dict)
                    healed = True

    return healed
