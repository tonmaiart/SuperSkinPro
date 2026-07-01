"""Orphan scanning and resolution — pure data operations over
LayerStorageService weight dicts, keyed by bone NAME exactly like the rest
of layer storage. The only thing "stable UUID" adds is the ability to
classify an orphaned name as likely-renamed (a live bone still carries the
UUID last associated with that name) vs. truly deleted (no bone does).

No automatic remap/delete ever happens here — every function is a single
explicit action invoked by the user through the resolve operator.
"""

from ...core_subsystems.layer_compositor import LayerCompositor as _LC
from . import armature_ids


def backfill_uuid_map(storage, obj, arm_obj) -> dict:
    """Stamp UUIDs onto every live deform bone and refresh the mesh-side
    ``{uuid: last_known_vg_name}`` snapshot. Purely additive."""
    uuid_map = storage.read_bone_uuid_map()
    if arm_obj:
        for vg in obj.vertex_groups:
            bone = arm_obj.data.bones.get(vg.name)
            if bone:
                bone_uuid = armature_ids.get_or_create_bone_id(bone)
                uuid_map[bone_uuid] = vg.name
    storage.write_bone_uuid_map(uuid_map)
    return uuid_map


def scan_orphans(storage, obj, arm_obj) -> list:
    """Return one entry per orphaned bone NAME (not per layer):
    ``{"name", "classification", "suggested_target", "layer_indices"}``.

    A bone is reported exactly as long as at least one layer's weight data
    still references its name — the instant every layer's data for that
    name is gone (resolved via remap/delete, or simply painted away to
    zero and pruned), it stops appearing here on the next scan with no
    extra bookkeeping needed.

    ``classification`` is ``"RENAMED"`` when a live bone still carries the
    UUID last associated with that name (a target is suggested, never
    auto-applied), otherwise ``"ORPHANED"``. ``layer_indices`` lists every
    layer slot index whose weight data references this name, so resolve
    actions can act across all of them at once.
    """
    live_names = {vg.name for vg in obj.vertex_groups}

    # {bone_name: [layer_index, ...]}
    name_to_layers: dict = {}
    for layer_idx, raw in storage.harvest_layer_data_map().items():
        decoded = _LC.decode(raw)
        names_in_layer = set()
        for weights in decoded.values():
            names_in_layer.update(weights.keys())
        for name in names_in_layer:
            name_to_layers.setdefault(name, []).append(layer_idx)

    orphan_names = sorted(set(name_to_layers.keys()) - live_names)
    if not orphan_names:
        return []

    uuid_map = storage.read_bone_uuid_map()  # {uuid: last_known_name}
    name_to_uuid = {name: u for u, name in uuid_map.items()}

    results = []
    for name in orphan_names:
        suggestion = None
        bone_uuid = name_to_uuid.get(name)
        if bone_uuid and arm_obj:
            bone = armature_ids.resolve_bone_by_uuid(arm_obj, bone_uuid)
            if bone and bone.name in live_names:
                suggestion = bone.name
        results.append({
            "name": name,
            "classification": "RENAMED" if suggestion else "ORPHANED",
            "suggested_target": suggestion,
            "layer_indices": name_to_layers[name],
        })
    return results


def delete_bone_weights(storage, meta_list, source_name: str, layer_index: int = None):
    """Remove *source_name*'s weight entries entirely.

    Scoped to *layer_index* when given, otherwise every layer in *meta_list*."""
    layers = meta_list if layer_index is None else [
        l for l in meta_list if l["index"] == layer_index
    ]
    for layer in layers:
        idx = layer["index"]
        layer_dict = storage.read_layer_dict(idx)
        changed = False
        for weights in layer_dict.values():
            if source_name in weights:
                del weights[source_name]
                changed = True
        if changed:
            storage.write_layer_dict(idx, layer_dict)
