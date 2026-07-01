"""BoneIdentityService — stable bone-UUID backfill, orphan scanning, and
explicit bone-weight delete for the active mesh.

Mirrors UIController's "instantiate per-operation" shape. The orphan scan
itself is a signature-gated cache (``scan_readonly``) rather than something
a caller must remember to explicitly trigger — an earlier revision scanned
only from specific call sites (entering Edit Mode) and went stale after any
event those call sites didn't cover (undo/redo of a remap/delete was the
one that shipped first). A signature-gated cache mirrors the existing
pattern in ``ui/utils.py``'s ``_get_visible_influence_bones`` (cheap key
check gates the expensive recompute).

As of the bones-list mirror-collection refactor (2026-06), the Deform
Bones list's orphan rows are no longer scanned directly from draw() —
they're read from ``obj.superskin_bones_collection`` (kept current by
``ui.utils.sync_bones_to_ui_collection``, called from the
``depsgraph_update_post`` / ``load_post`` handlers via
``get_scan_for_object``), the same mirror-collection pattern the Layers
list already used for its own JSON-backed metadata. ``scan_readonly`` /
``backfill_and_scan`` stay split because Blender forbids writing to ID
data (mesh custom properties, and the mirror CollectionProperty itself)
from inside a panel ``draw()`` callback — ``backfill_and_scan``'s
bone-UUID-map write raises ``AttributeError: Writing to ID classes in
this context is not allowed`` if called from there.
"""

from ..layer_storage.storage_service import LayerStorageService
from . import orphan_resolver

# {mesh_name: [orphan_dict, ...]}
_scan_cache: dict = {}
# {mesh_name: signature} — see _compute_signature
_scan_cache_key: dict = {}


def _find_armature(obj):
    return next(
        (m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object),
        None,
    )


def _compute_signature(storage, obj, arm_obj) -> tuple:
    """Cheap signature of everything orphan detection depends on: live
    vertex-group names, every layer's raw weight blob, and the live
    armature's bone names. A mismatch against the last scan's signature
    means something that could change orphan status actually changed, so
    it's safe to skip the real (more expensive, decode-every-layer) scan
    whenever this matches — same trade-off as
    ``_get_visible_influence_bones``'s ``hash(raw_blob)`` key, just
    extended across every layer instead of only the active one, since an
    orphan can hide in any layer."""
    vg_names = tuple(sorted(vg.name for vg in obj.vertex_groups))
    layer_blobs = tuple(sorted(storage.harvest_layer_data_map().items()))
    arm_names = tuple(sorted(b.name for b in arm_obj.data.bones)) if arm_obj else ()
    return (vg_names, hash(layer_blobs), arm_names)


class BoneIdentityService:
    def __init__(self, context, obj=None):
        """*context* may be ``None`` when *obj* is passed explicitly — only
        ``delete_bone`` (which builds a real ``UIController``)
        needs a live ``context``; the read-only scan path doesn't."""
        self.ctx = context
        self.obj = obj if obj is not None else (context.active_object if context else None)
        if not self.obj or self.obj.type != 'MESH':
            raise ValueError("No active mesh object")
        self.storage = LayerStorageService(self.obj.data)
        self.arm_obj = _find_armature(self.obj)

    def scan_readonly(self) -> list:
        """Return the current orphan list without writing anything to mesh
        data — the only variant safe to call from a panel ``draw()``
        callback. Blender raises ``AttributeError: Writing to ID classes
        in this context is not allowed`` on any ID-data write attempted
        during draw (this shipped once: an earlier revision called
        ``backfill_and_scan()``, including its ``write_bone_uuid_map()``
        write, directly from here).

        Signature-gated (see ``_compute_signature``) against the same
        cache ``backfill_and_scan()`` populates, so this only recomputes
        when something that could change orphan status actually changed
        since the last scan by *either* method — cheap enough to call on
        every redraw.
        """
        key = self.obj.data.name
        sig = _compute_signature(self.storage, self.obj, self.arm_obj)
        if _scan_cache_key.get(key) == sig and key in _scan_cache:
            return _scan_cache[key]

        result = orphan_resolver.scan_orphans(self.storage, self.obj, self.arm_obj)
        _scan_cache[key] = result
        _scan_cache_key[key] = sig
        return result

    def backfill_and_scan(self) -> list:
        """Scan for orphans AND refresh the bone-UUID map (a write) — only
        call this from an operator or app-handler, NEVER from draw() (see
        ``scan_readonly``'s docstring for why). Always does the real work
        when called instead of trusting the signature cache, since this is
        only invoked from infrequent write-context triggers (e.g.
        entering Edit Mode), not every redraw, so there's no per-redraw
        cost to gate — and skipping the write whenever a draw-time
        ``scan_readonly()`` happened to already match the signature would
        mean the uuid map might never get backfilled at all.

        Uses the uuid map as it stood at the END of the PREVIOUS backfill,
        THEN refreshes the map to the current live names for next time.
        Ordering matters: classifying an orphan as "renamed" depends on
        the map still holding the bone's PREVIOUSLY known name at scan
        time. Refreshing the map first would overwrite that old name with
        the live one before the comparison ever runs, making every rename
        look identical to a deletion — the same baseline-computed-after-
        the-mutation mistake documented in docs/bug-history/0011.
        """
        result = orphan_resolver.scan_orphans(self.storage, self.obj, self.arm_obj)
        orphan_resolver.backfill_uuid_map(self.storage, self.obj, self.arm_obj)
        key = self.obj.data.name
        _scan_cache[key] = result
        _scan_cache_key[key] = _compute_signature(self.storage, self.obj, self.arm_obj)
        return result

    def delete_bone(self, source_name: str, layer_index: int = None):
        """Remove *source_name*'s weight entirely, across every layer (or
        just *layer_index* if given)."""
        from ..facade import CoreFacade
        facade = CoreFacade(self.ctx)
        meta_list = self.storage.read_meta_list()
        orphan_resolver.delete_bone_weights(
            self.storage, meta_list, source_name, layer_index=layer_index
        )
        facade.finish()

    @staticmethod
    def get_scan_for_object(obj) -> list:
        """Single source of truth for orphan rows, driven by *obj* alone —
        for handler-driven callers (``ui.utils.sync_bones_to_ui_collection``,
        invoked from ``depsgraph_update_post`` / ``load_post``) that iterate
        every SuperSkinPro-managed mesh in the scene, not just whichever
        one happens to be ``context.active_object`` at that moment. Routes
        through the signature-gated ``scan_readonly()`` / ``_scan_cache``,
        so it recomputes automatically whenever vertex-group names, any
        layer's weight data, or the live armature's bone set actually
        changed since the last scan — entering Edit Mode, undo/redo, and a
        live bone rename all just work without a dedicated call site for
        each, and repeated calls for the same unchanged mesh are cheap."""
        if not obj or obj.type != 'MESH':
            return []
        try:
            return BoneIdentityService(None, obj=obj).scan_readonly()
        except ValueError:
            return []

    @staticmethod
    def clear_scan_cache():
        _scan_cache.clear()
        _scan_cache_key.clear()
