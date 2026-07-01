"""LayerManager — stateless pure-data dispatcher for the multi-layer stack.

Every method accepts plain Python structures (list, dict, str, int) and
returns modified copies — never touches Blender's data model.  The UI
Controller is the sole bridge: it harvests Blender data, calls methods
here, and writes results back.

All meta_list operations expect the list in **display order** (topmost
layer first, base layer last) — the same order produced by
``json.loads(ss_layers_meta)``.
"""

class LayerManager:
    """Stateless CRUD + query operations on the layer metadata stack."""

    # ═════════════════════════════════════════════════════════════════
    #  Query helpers
    # ═════════════════════════════════════════════════════════════════

    def layers(self, meta_list):
        """Return the metadata list as-is (convenience pass-through)."""
        return meta_list

    def layer_names(self, meta_list):
        """Return ``[layer_name, ...]`` in display order."""
        return [l["name"] for l in meta_list]

    def active_layer_name(self, meta_list, active_index):
        """Return the name of the layer whose slot equals *active_index*."""
        for l in meta_list:
            if l["index"] == active_index:
                return l["name"]
        return "Base"

    def _next_index(self, meta_list):
        """Return the next available layer index (> max existing)."""
        return max((l["index"] for l in meta_list), default=0) + 1

    # ═════════════════════════════════════════════════════════════════
    #  CRUD
    # ═════════════════════════════════════════════════════════════════

    def create_layer(self, meta_list, name):
        """Insert a new layer at the top of the stack.

        Returns:
            ``(new_meta_list, new_index)`` — *new_meta_list* is a shallow
            copy; the caller must handle layer-data initialisation.
        """
        meta = list(meta_list)  # shallow copy
        new_idx = self._next_index(meta)
        entry = {
            "name": name,
            "index": new_idx,
            "visible": True,
            "bone_locks": {},
            "mask_default": 0.0,
            "bone_selection": ",",
            "active_bone": "",
        }
        meta.insert(0, entry)  # top of display stack
        return meta, new_idx

    def remove_layer(self, meta_list, index):
        """Remove a layer by its slot *index*.

        Every layer has equal rights — only the last remaining layer
        cannot be removed (the system must always have at least one).

        Returns:
            ``new_meta_list`` (shallow copy with the entry removed, or
            unchanged if this was the only layer left).
        """
        if len(meta_list) <= 1:
            return list(meta_list)
        return [l for l in meta_list if l["index"] != index]

    def duplicate_layer(self, meta_list, index):
        """Clone a layer's metadata, inserting the copy above the source.

        Returns:
            ``(new_meta_list, new_index)`` — the caller is responsible for
            cloning the actual weight / mask data blobs.
        """
        meta = list(meta_list)
        pos = next((i for i, l in enumerate(meta) if l["index"] == index), None)
        if pos is None:
            return meta, None

        src = meta[pos]
        new_idx = self._next_index(meta)
        new_entry = {
            "name": f"{src['name']} Copy",
            "index": new_idx,
            "visible": True,
            "bone_locks": dict(src.get("bone_locks", {})),
            "mask_default": src.get("mask_default", 1.0),
            "bone_selection": src.get("bone_selection", ","),
            "active_bone": src.get("active_bone", ""),
        }
        meta.insert(pos, new_entry)
        return meta, new_idx

    def move_layer(self, meta_list, index, direction):
        """Shift a layer one position in display order.

        Args:
            direction: ``-1`` for up (toward top of stack),
                       ``+1`` for down (toward bottom of stack).

        Every layer has equal rights — any layer can be moved freely.
        Attempting to move past either edge of the stack is a no-op.

        Returns:
            ``new_meta_list`` (shallow copy).  If the move was blocked by an
            edge boundary the returned list is identical to the input.
        """
        meta = list(meta_list)

        # Locate the layer in display order
        pos = next((i for i, l in enumerate(meta) if l["index"] == index), None)
        if pos is None:
            return meta  # layer not found — nothing to move

        target_pos = pos + direction

        # Absolute stack edges
        if target_pos < 0 or target_pos >= len(meta):
            return meta

        # Perform the swap: pop at pos, insert at target_pos.
        meta.insert(target_pos, meta.pop(pos))
        return meta

    def toggle_visible(self, meta_list, index):
        """Flip the ``visible`` flag of *index*.

        Returns a modified shallow copy.
        """
        meta = list(meta_list)
        for l in meta:
            if l["index"] == index:
                l["visible"] = not l.get("visible", True)
                break
        return meta

    def rename_layer(self, meta_list, index, new_name):
        """Rename a layer.

        Returns a modified shallow copy.
        """
        meta = list(meta_list)
        for l in meta:
            if l["index"] == index:
                l["name"] = new_name
                break
        return meta

    # ═════════════════════════════════════════════════════════════════
    #  Private field-access helpers
    # ═════════════════════════════════════════════════════════════════

    def _get_field(self, meta_list, layer_index, field, default):
        """Return ``layer[field]`` for *layer_index*, or *default*."""
        for l in meta_list:
            if l["index"] == layer_index:
                return l.get(field, default)
        return default

    def _set_field(self, meta_list, layer_index, field, value):
        """Set ``layer[field] = value`` and return a modified shallow copy."""
        meta = list(meta_list)
        for l in meta:
            if l["index"] == layer_index:
                l[field] = value
                break
        return meta

    # ═════════════════════════════════════════════════════════════════
    #  Per-layer bone locks
    # ═════════════════════════════════════════════════════════════════

    def get_bone_locks(self, meta_list, layer_index):
        """Return ``{bone_name: bool}`` lock dict for *layer_index*."""
        return self._get_field(meta_list, layer_index, "bone_locks", {})

    def set_bone_locks(self, meta_list, layer_index, bone_locks):
        """Persist ``{bone_name: bool}`` into layer metadata.

        Returns a modified shallow copy.
        """
        return self._set_field(meta_list, layer_index, "bone_locks", dict(bone_locks))

    # ═════════════════════════════════════════════════════════════════
    #  Per-layer bone selection
    # ═════════════════════════════════════════════════════════════════

    def get_selected_bones(self, meta_list, layer_index):
        """Return the comma-separated selected-names string.

        Format: ``\",bone1,bone2,\"`` — same as ``superskin_storage.selected_names``.
        """
        return self._get_field(meta_list, layer_index, "bone_selection", ",")

    def set_selected_bones(self, meta_list, layer_index, selected_names):
        """Persist *selected_names* into layer metadata.

        Returns a modified shallow copy.
        """
        val = str(selected_names) if selected_names else ","
        if not val.startswith(","):
            val = "," + val
        return self._set_field(meta_list, layer_index, "bone_selection", val)

    # ═════════════════════════════════════════════════════════════════
    #  Per-layer active bone (focal target)
    # ═════════════════════════════════════════════════════════════════

    def get_active_bone_name(self, meta_list, layer_index):
        """Return the saved active-bone name, or ``\"\"``."""
        return self._get_field(meta_list, layer_index, "active_bone", "")

    def set_active_bone_name(self, meta_list, layer_index, name):
        """Persist *name* as the active bone for *layer_index*.

        Returns a modified shallow copy.
        """
        return self._set_field(meta_list, layer_index, "active_bone", str(name) if name else "")

    def find_mask_gaps(self, meta_list, mask_dicts_map, num_verts) -> list:
        """Identify vertices where accumulated mask coverage falls below 1.0.

        Walks the layer stack top-to-bottom, accumulating the alpha-over
        coverage product. A vertex is considered a "gap" when the residual
        leak (1 - accumulated_coverage) remains above 0.001 after all
        visible layers have been processed.

        Args:
            meta_list: Layer metadata list in display order (topmost first),
                as produced by ``json.loads(ss_layers_meta)``.
            mask_dicts_map: ``{layer_index: {v_idx: float}}`` — decoded mask
                data for every layer. Missing entries fall back to the
                layer's ``mask_default``.
            num_verts: Total vertex count of the mesh.

        Returns:
            ``list[int]`` — vertex indices where accumulated coverage < 0.999.
        """
        # Start with full leak (1.0 = vertex is completely uncovered).
        opacity_leak = [1.0] * num_verts

        for layer in meta_list:
            if not layer.get("visible", True):
                continue

            l_idx = layer["index"]
            mask_dict = mask_dicts_map.get(l_idx, {})
            mask_default = float(layer.get("mask_default", 1.0))

            for v_idx in range(num_verts):
                v_mask = mask_dict.get(v_idx, mask_default)
                v_mask = max(0.0, min(1.0, v_mask))
                opacity_leak[v_idx] *= (1.0 - v_mask)

        return [v_idx for v_idx, leak in enumerate(opacity_leak) if leak > 0.001]


# ═══════════════════════════════════════════════════════════════════════════
#  Module-level helpers — comma-separated selection pool on
#  ``obj.superskin_storage.selected_names``
# ═══════════════════════════════════════════════════════════════════════════

def add_vg_selected(obj, name):
    """Add *name* to the comma-separated selection pool if not already present.

    Returns True if the name was actually added.
    """
    storage = obj.superskin_storage
    # Normalize: must always start AND end with ","
    if not storage.selected_names or not storage.selected_names.startswith(","):
        storage.selected_names = ","
    if f",{name}," not in storage.selected_names:
        storage.selected_names += f"{name},"
        return True
    return False


def remove_vg_selected(obj, name):
    """Remove *name* from the comma-separated selection pool.

    Returns True if the name was actually removed.
    """
    storage = obj.superskin_storage
    if f",{name}," in storage.selected_names:
        storage.selected_names = storage.selected_names.replace(f"{name},", "")
        return True
    return False


def clear_all_selected(obj):
    """Reset the selection pool to the empty sentinel ``\",\"``."""
    obj.superskin_storage.selected_names = ","
