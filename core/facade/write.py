"""WriteFacadeMixin — all state-mutation, storage-commit, and flatten operations.

Methods here may modify layer storage or trigger mesh vertex group commits.

finish() is implemented inline, passing self (CoreFacade) as the ctrl-compatible
argument to pipeline.flatten_to_mesh_edit(). CoreFacade's public proxy properties
(obj, mesh, storage, shader_mgr) satisfy the attribute contract pipeline expects.

write_active_layer_from_calc() accepts int-keyed layer data (direct Rust output)
and converts it via RustWeightEngine's data-bridge static methods without a
string->int->string round-trip.

write_active_layer() and write_layer_dict() / write_mask_dict() delegate to
_write_active_layer_string() for orphan-merge / temp-VG routing logic.

_normalize_orphan_budget() and _purge_zeroed_orphans_from_all_layers() are
module-level helpers used exclusively by _write_active_layer_string().
"""

from ...core_subsystems.rust_weight_engine import RustWeightEngine
from ..ui_controller import pipeline


# ── Orphan budget helpers ─────────────────────────────────────────────────────

def _normalize_orphan_budget(layer_str: dict, known_bone_names: set) -> None:
    """Scale orphaned bone weights down so total weight per vertex stays <= 1.0."""
    for weights in layer_str.values():
        known_total = sum(w for name, w in weights.items() if name in known_bone_names)
        orphan_total = sum(w for name, w in weights.items() if name not in known_bone_names)
        if orphan_total <= 0.0:
            continue
        orphan_budget = max(0.0, 1.0 - known_total)
        if orphan_total <= orphan_budget:
            continue
        scale = orphan_budget / orphan_total
        for name in list(weights):
            if name not in known_bone_names:
                weights[name] = weights[name] * scale


def _purge_zeroed_orphans_from_all_layers(storage, orphan_entries: dict,
                                           written_layer_str: dict) -> None:
    """Remove orphaned bones fully zeroed from the active layer across all other layers."""
    orphan_names: set = set()
    for v_weights in orphan_entries.values():
        orphan_names.update(v_weights.keys())

    still_present: set = set()
    for v_weights in written_layer_str.values():
        still_present.update(v_weights.keys())

    fully_zeroed = orphan_names - still_present
    if not fully_zeroed:
        return

    from ...core_subsystems.rust_weight_engine import RustWeightEngine as _RWE

    active_idx = storage.get_active_layer_index()
    meta_list = storage.read_meta_list()

    for layer in meta_list:
        idx = layer["index"]
        if idx == active_idx:
            continue
        layer_dict = storage.read_layer_dict(idx)
        changed = False
        for v_weights in layer_dict.values():
            for bone_name in fully_zeroed:
                if bone_name in v_weights:
                    del v_weights[bone_name]
                    changed = True
        if changed:
            _RWE.prune_zero_bones(layer_dict)
            storage.write_layer_dict(idx, layer_dict)

    meta_changed = False
    for layer in meta_list:
        locks = layer.get("bone_locks", {})
        new_locks = {k: v for k, v in locks.items() if k not in fully_zeroed}
        if new_locks != locks:
            layer["bone_locks"] = new_locks
            meta_changed = True

        sel = layer.get("bone_selection", ",")
        new_sel = sel
        for bone_name in fully_zeroed:
            new_sel = new_sel.replace(f"{bone_name},", "")
        if new_sel != sel:
            layer["bone_selection"] = new_sel
            meta_changed = True

        if layer.get("active_bone", "") in fully_zeroed:
            layer["active_bone"] = ""
            meta_changed = True

    if meta_changed:
        storage.write_meta_list(meta_list)


class WriteFacadeMixin:
    """Mixin providing write access to layer storage and flatten pipeline."""

    def write_layer_dict(self, layer_dict: dict):
        self.storage.write_layer_dict(self.active_layer_index, layer_dict)

    def write_mask_dict(self, mask_dict: dict):
        self.storage.write_mask_dict(self.active_layer_index, mask_dict)

    def finish(self, *, color_only: bool = False):
        """Reflatten layers to mesh vertex groups and request a viewport redraw.

        Routes through pipeline.flatten_to_mesh_edit() when in EDIT mode,
        passing self (the facade) as the ctrl-compatible object. The facade's
        public proxy properties (obj, mesh, storage, shader_mgr) satisfy the
        attribute contract that pipeline functions expect.

        Args:
            color_only: When True, only the colour VBO is invalidated. Use for
                weight-paint strokes where mesh topology is unchanged.
        """
        if self._obj.mode == 'EDIT':
            pipeline.flatten_to_mesh_edit(self)
        else:
            self._storage.flatten_visible_layers_to_mesh(self._obj)
        self._mesh.update()
        self._obj.update_tag()
        self._shader_mgr.bump_deform_generation()
        if color_only:
            self._shader_mgr.invalidate_color_only()
        else:
            self._shader_mgr.invalidate_and_redraw()

    def finish_color_only(self):
        self.finish(color_only=True)

    def write_active_layer(self, layer_str: dict, *, color_only: bool = True) -> None:
        """Write a string-keyed layer dict to the correct target for the current
        mode, then call finish().

        In Edit Mode, writes to __ssp_* BMesh temp VGs. Outside Edit Mode,
        writes to ss_layer_N. Handles orphan re-merge and zero-weight pruning
        via the underlying _write_active_layer_string path.

        Args:
            layer_str: {v_idx (int): {bone_name (str): weight (float)}}
            color_only: Passed to finish(). True when topology is unchanged
                (typical for weight-paint brush strokes).

        Call read_active_layer() first on this instance so the bone mapping
        cache is populated; otherwise the mapping is computed fresh.
        """
        if not hasattr(self, '_bone_to_id') or not hasattr(self, '_id_to_bone'):
            self.get_unified_mapping()
        result_int = {
            v_idx: {self._bone_to_id[b]: w for b, w in weights.items() if b in self._bone_to_id}
            for v_idx, weights in layer_str.items()
        }
        self._write_active_layer_string(result_int, self._id_to_bone, {}, is_mask_mode=False)
        self.finish(color_only=color_only)

    def _write_active_layer_string(self, layer_int: dict, id_to_bone: dict,
                                    mask_dict: dict = None, *,
                                    is_mask_mode: bool = False):
        """Convert int-keyed layer data, merge orphans, prune zeros, and persist.

        Routes to __ssp_* BMesh temp VGs in EDIT mode; otherwise writes to
        ss_layer_N via storage.save_active(). Orphan re-merge and budget
        normalization are applied before writing.
        """
        from ..layer_storage.temp_vg_bridge import has_temp_vgs, write_layer_to_temp_vgs_bm

        layer_str = RustWeightEngine.map_layer_to_string(layer_int, id_to_bone)
        orphan_entries = getattr(self, "_orphan_entries", {})
        for v_idx, orphan_weights in orphan_entries.items():
            layer_str.setdefault(v_idx, {}).update(orphan_weights)
        if not is_mask_mode:
            known_bone_names = {name for idx, name in id_to_bone.items()
                                if idx < len(self.obj.vertex_groups)}
            _normalize_orphan_budget(layer_str, known_bone_names)
        RustWeightEngine.prune_zero_bones(layer_str)

        if self.obj.mode == 'EDIT':
            if has_temp_vgs(self.obj):
                write_layer_to_temp_vgs_bm(
                    self.obj, self.mesh, layer_str, id_to_bone, mask_dict
                )
                if not is_mask_mode and orphan_entries:
                    _purge_zeroed_orphans_from_all_layers(self.storage, orphan_entries, layer_str)
                return

        self.storage.save_active(layer_str, mask_dict, is_mask_mode=is_mask_mode)
        if not is_mask_mode and orphan_entries:
            _purge_zeroed_orphans_from_all_layers(self.storage, orphan_entries, layer_str)

    def write_active_layer_from_calc(self, layer_int: dict, id_to_bone: dict) -> None:
        """Write an integer-keyed layer dict (direct Rust output) to the correct
        target for the current mode.

        Converts int-keyed data to string format via data_bridge, prunes zero
        bones, then writes through the appropriate path.

        In EDIT mode this performs a dual-update:
          1. Temp VGs (``__ssp_*``) are updated so Blender's native Weight
             Overlay shows the active layer's weights in real-time.
          2. All visible layers are composited and written directly into the
             real deformation vertex groups on the edit-bmesh, so the Armature
             modifier recalculates viewport deform immediately.

        The caller does NOT need to call finish() afterwards — the viewport
        refresh is handled inline.

        Persistence of temp VG data back to ``ss_layer_N`` storage only occurs
        during a deliberate Save Weight operation (``_exit_edit_mode``).

        This method handles only weight writes (not mask writes). Use
        write_active_layer() for the full string-keyed path that includes orphan
        re-merging.

        Args:
            layer_int: {v_idx (int): {vg_index (int): weight (float)}}
            id_to_bone: {vg_index (int): bone_name (str)}
        """
        layer_str = RustWeightEngine.map_layer_to_string(layer_int, id_to_bone)
        RustWeightEngine.prune_zero_bones(layer_str)

        if self._obj.mode == 'EDIT':
            from ..layer_storage.temp_vg_bridge import has_temp_vgs, write_layer_to_temp_vgs_bm
            if has_temp_vgs(self._obj):
                # 1. Update temp VGs so the native Weight Overlay sees the
                #    active layer's weights in real-time.
                write_layer_to_temp_vgs_bm(self._obj, self._mesh, layer_str, id_to_bone)

                # 2. Composite all visible layers and write the final evaluated
                #    result directly into the real deformation VGs on the edit-
                #    bmesh. This triggers an immediate Armature modifier update
                #    so the viewport deform reflects the weight change.
                pipeline.flatten_to_mesh_edit(self)

                # 3. Force the evaluated mesh and all 3D viewports to refresh.
                import bpy as _bpy
                self._obj.update_from_editmode()
                self._shader_mgr.bump_deform_generation()
                self._obj["__ssp_deform_gen"] = self._obj.get("__ssp_deform_gen", 0) + 1
                for window in _bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
                return

        self._storage.save_active(layer_str, is_mask_mode=self.is_mask_context())
