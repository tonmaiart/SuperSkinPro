"""Mirror-weight logic — Rust Accelerated Multi-OS Portal.

Combines name-pair generation with the layer-aware mirror operation.

⚡ LOCAL ID MAPPING:
- ``generate_pairs`` remains string-based (pattern matching needs bone names)
- ``apply`` and ``apply_mask`` use Integer Bone IDs for inner layer_dict keys

⚡ GAP-FILL FALLBACK:
- ``apply`` / ``apply_mask_flat`` return ``(result, gap_v_indices)``. The Rust
  nearest-vertex pass is unchanged and still wins whenever a match exists
  within tolerance; ``gap_v_indices`` lists only the target-side vertices it
  couldn't resolve (e.g. asymmetric topology). ``_fill_weight_gaps`` /
  ``_fill_mask_gaps`` below fill exactly those, via the same "closest point
  on surface + barycentric blend" approach as
  ``features/weight_transfer/transfer_core.py``, so exact-match vertices are
  never touched or softened.

⚡ TOPOLOGY-BASED SIDE CLASSIFICATION:
- ``apply`` / ``apply_mask_flat`` both take a ``target_side_mask`` — a
  per-vertex bool list from ``classify_sides_by_topology()``, NOT a raw
  coordinate-sign test. When the mesh visually intersects across the mirror
  plane (e.g. an oversized pant leg poking into the other leg), a vertex
  that's topologically part of one side can have a coordinate that dips
  onto the other — confirmed by a user report where the mirrored weight
  data itself (not just its rendering) was wrong right in the overlap
  region. The mask is computed once per pipeline run and shared by both
  channels and the gap-fill fallback's source-side surface.
"""

import heapq

from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

from ...core.facade import CoreFacade


def get_bone_centers(core_facade):
    """Compute world-space bone centre positions keyed by vertex-group name.

    Replaces the UIController._bone_centers escape hatch — parametrized over
    CoreFacade so that core/ui_controller/ carries no feature-specific logic.
    """
    obj = core_facade.get_obj()
    arm_obj = next(
        (m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object), None
    )
    centers = {}
    arm_mat = arm_obj.matrix_world if arm_obj else None
    for vg in core_facade.get_vertex_groups():
        if arm_obj and arm_mat:
            bone = arm_obj.data.bones.get(vg.name)
            if bone:
                centers[vg.name] = (
                    arm_mat @ ((bone.head_local + bone.tail_local) * 0.5)
                ).to_tuple()
        # Vertex groups without a matching bone are omitted rather than set
        # to None — the Rust FFI signature requires (f64, f64, f64) tuples
        # for every value, and a missing key is already handled on that side.
    return centers


def classify_sides_by_topology(core_facade, axis_idx, direction, margin_frac=0.15):
    """Classify every vertex as source-side or target-side using geodesic
    (edge-length-weighted) distance along the mesh surface, not a raw
    coordinate-sign test.

    A coordinate-sign split misclassifies vertices whenever the mesh
    visually folds/intersects across the mirror plane — e.g. a vertex
    that's topologically part of the target side (say, the right leg) can
    have a coordinate that dips into source territory because the geometry
    pokes through the other leg there. Confirmed by a user report where the
    mirrored *weight data itself* (not just its rendering) was wrong right
    in the overlap region, using a pure coordinate-sign split.

    Two prior approaches were tried and both regressed on real models:
      - **Fixed-margin multi-seed BFS (hop-count):** seeded every vertex
        beyond a small coordinate margin, flood-filled by edge-hop count.
        A vertex poking deep enough past the plane exceeded that small
        margin and self-seeded on the wrong side directly, poisoning the
        flood-fill — confirmed: light overlap fixed, heavy overlap still
        misclassified.
      - **Single global extreme-vertex anchor per side (Dijkstra):** used
        exactly the single most-extreme vertex on each side as the only
        seed, reasoning an intersection can't push a vertex further out
        than the model's own true extremity. This backfired badly: if
        *any other, unrelated part* of the mesh (e.g. a trunk or ear) has a
        more extreme coordinate than the leg region itself, the anchor
        lands there instead — geodesic distance from a far-away anchor is
        then dominated by "distance to travel there" (similar for both
        legs), destroying local discrimination. Confirmed: previously-fixed
        areas broke again after this change.
      - Nearest-*bone*-position was also considered (bones don't self-
        intersect the way skin does) but is mathematically a dead end for
        symmetric rigs: distance-to-nearest-of-two-mirror-symmetric-points
        reduces algebraically to comparing the vertex's own raw coordinate
        sign — identical to the naive test that started this investigation,
        with zero added robustness.

    Current approach: multi-seed (not a single global anchor — keeps
    classification local to each body part) with a WIDE margin (15% of the
    mesh's own extent along the axis, not a tiny epsilon) so a *localized*
    bulge — a small fraction of a limb's own length/depth — can't clear the
    margin and self-seed wrong, while genuinely far-out vertices (the bulk
    of any limb) still seed correctly nearby. Propagation is Dijkstra over
    actual edge lengths (geodesic surface distance), not raw hop-count, for
    better accuracy on irregular mesh density. A vertex whose connected
    component has no reachable seed at all (rare — a fully disconnected
    island entirely within the margin band) falls back to its own raw
    coordinate sign as a last resort.

    Known remaining limitation: an intersection so severe that it consumes
    a large fraction of the limb's own length (wide) or pokes deeper than
    the margin allows (deep) can still be misclassified — there is no
    purely-geometric way to fully resolve that without extra information
    (e.g. the pre-deformation rest pose), only mitigate it.

    Returns a list of bool, length == vertex count, True == target side.
    """
    mesh = core_facade.get_mesh()
    num_verts = len(mesh.vertices)
    positions = [v.co.copy() for v in mesh.vertices]
    axis_vals = [p[axis_idx] for p in positions]

    span = max((abs(c) for c in axis_vals), default=0.0)
    margin = max(span * margin_frac, 1e-4)

    def _raw_side(c):
        if direction == 'POS_NEG':
            return c < 0
        return c > 0

    adjacency = [[] for _ in range(num_verts)]
    for e in mesh.edges:
        a, b = e.vertices[0], e.vertices[1]
        length = (positions[a] - positions[b]).length
        adjacency[a].append((b, length))
        adjacency[b].append((a, length))

    UNKNOWN = -1
    label = [UNKNOWN] * num_verts
    dist = [float('inf')] * num_verts
    heap = []

    for v_idx, c in enumerate(axis_vals):
        if abs(c) >= margin:
            label[v_idx] = 1 if _raw_side(c) else 0
            dist[v_idx] = 0.0
            heapq.heappush(heap, (0.0, v_idx))

    while heap:
        d, v_idx = heapq.heappop(heap)
        if d > dist[v_idx]:
            continue
        for n, length in adjacency[v_idx]:
            nd = d + length
            if nd < dist[n]:
                dist[n] = nd
                label[n] = label[v_idx]
                heapq.heappush(heap, (nd, n))

    for v_idx, c in enumerate(axis_vals):
        if label[v_idx] == UNKNOWN:
            label[v_idx] = 1 if _raw_side(c) else 0

    return [lbl == 1 for lbl in label]


def generate_pairs(vg_names, bone_centers, sr_list, axis, direction):
    """Build mirror name pairs from search/replace rules (string-based)."""
    rust = CoreFacade.get_rust_gateway("mirror_generate_pairs")
    result = rust.call(
        "rust_mirror_generate_pairs",
        vg_names,
        bone_centers,
        sr_list,
        axis,
        direction,
    )
    return {str(k): str(v) for k, v in result.items()}


def apply(layer_dict, id_pairs, vertex_groups_lock, vertex_coords, target_side_mask, axis, direction):
    """Layer-aware mirror with centre-plane splitting operating on Integer Bone IDs.

    All bone references are already integer vertex-group indices when they
    arrive here — UIController converted name_pairs→id_pairs upstream.

    Args:
        layer_dict: ``{v_idx: {bone_id: weight}}`` (int→int→float)
        id_pairs: ``{src_bone_id: tgt_bone_id}``
        vertex_groups_lock: ``{bone_id: bool}``
        target_side_mask: per-vertex bool list from ``classify_sides_by_topology()``
            — see module docstring's "TOPOLOGY-BASED SIDE CLASSIFICATION".

    Returns:
        ``(result, gap_v_indices)`` — see module docstring's "GAP-FILL FALLBACK".
    """
    if not id_pairs:
        return layer_dict, []

    layer_dict = {k: dict(v) for k, v in layer_dict.items()}

    rust = CoreFacade.get_rust_gateway("mirror_apply")
    result, gap_v_indices = rust.call(
        "rust_mirror_apply",
        layer_dict,
        id_pairs,
        vertex_groups_lock,
        vertex_coords,
        target_side_mask,
        axis,
        direction,
    )
    return {int(k): dict(v) for k, v in result.items()}, [int(v) for v in gap_v_indices]


def apply_mask(mask_dict, vertex_coords, axis, direction):
    """Mirror mask values across axis — no bone dimension.

    Args:
        mask_dict: ``{v_idx: float}``
    """
    rust = CoreFacade.get_rust_gateway("mirror_apply_mask")
    result = rust.call(
        "rust_mirror_apply_mask",
        mask_dict,
        vertex_coords,
        axis,
        direction,
    )
    return {k: v for k, v in result.items()}


def apply_mask_flat(mask_dict: dict, vertex_coords: list, target_side_mask: list,
                    axis: str, direction: str,
                    num_verts: int) -> tuple:
    """⚡ Zero-copy flat-array mirror mask via CSR bridge.

    *target_side_mask* — see ``apply()``'s and the module docstring's
    "TOPOLOGY-BASED SIDE CLASSIFICATION".

    Returns ``(mask_dict, gap_v_indices)`` — see module docstring's
    "GAP-FILL FALLBACK". ``mask_dict`` is int-keyed.
    """
    rust = CoreFacade.get_rust_gateway("mirror_apply_mask_flat")
    _bridge = CoreFacade.get_flat_array_bridge()
    mask_flat = _bridge.mask_to_flat(mask_dict, num_verts, sentinel=_bridge.MASK_SENTINEL)
    res_mask_flat, gap_v_indices = rust.call(
        "rust_mirror_apply_mask_flat",
        mask_flat, vertex_coords, target_side_mask, axis, direction,
    )
    result = _bridge.flat_to_mask(res_mask_flat, sentinel=_bridge.MASK_SENTINEL)
    return result, [int(v) for v in gap_v_indices]


_AXIS_IDX = {"X": 0, "Y": 1, "Z": 2}


def build_local_surface(core_facade):
    """Local-space triangulated BVH of the *whole* active mesh (both sides).

    Used only by ``check_self_intersection``, which genuinely needs both
    sides of the surface to detect where they cross. Local space (not
    world) matches the coordinate space ``vertex_coords`` already uses
    everywhere else in this module.

    ⚠️ Do NOT reuse this for the gap-fill fallback — see
    ``build_source_side_surface`` for why.
    """
    mesh = core_facade.get_mesh()
    mesh.calc_loop_triangles()
    positions = [Vector(v.co) for v in mesh.vertices]
    triangles = [tuple(lt.vertices) for lt in mesh.loop_triangles]
    bvh = BVHTree.FromPolygons(positions, triangles, all_triangles=True)
    return bvh, triangles, positions


def build_source_side_surface(core_facade, target_side_mask):
    """Local-space triangulated BVH of the source side ONLY, for the gap-fill
    fallback (see module docstring's "GAP-FILL FALLBACK").

    A whole-mesh BVH is wrong here whenever the source and target sides
    physically overlap (e.g. an oversized pant leg intersecting the other
    leg, ``check_self_intersection``'s exact scenario): the flipped query
    point can end up geometrically closer to the target side's own folded
    geometry than to the true mirrored source point, bleeding in weight
    data from the wrong side entirely (confirmed by a visible "spiky" weight
    artifact on an intersecting model). Restricting the BVH to triangles
    with all 3 vertices on the source side guarantees the nearest point
    found can only ever come from the source, regardless of how much the
    target side overlaps it in space.

    *target_side_mask* must be the same ``classify_sides_by_topology()``
    result used everywhere else in the pipeline — a raw coordinate-sign test
    here would reintroduce the exact same misclassification problem in the
    intersecting region that motivated topology-based classification in the
    first place.

    Returns ``None`` if the mesh has no fully source-side triangle (nothing
    for the fallback to blend from).
    """
    mesh = core_facade.get_mesh()
    mesh.calc_loop_triangles()
    positions = [Vector(v.co) for v in mesh.vertices]
    triangles = [
        tuple(lt.vertices) for lt in mesh.loop_triangles
        if all(not target_side_mask[i] for i in lt.vertices)
    ]
    if not triangles:
        return None
    bvh = BVHTree.FromPolygons(positions, triangles, all_triangles=True)
    return bvh, triangles, positions


def _flip_point(coord, axis_idx):
    flipped = list(coord)
    flipped[axis_idx] = -flipped[axis_idx]
    return Vector(flipped)


def _fill_weight_gaps(layer_dict_before, result, gap_v_indices, id_pairs,
                       vertex_coords, axis_idx, surface, vertex_groups_lock):
    """BVH + barycentric fallback for the bone-weight channel's gaps.

    Mirrors ``transfer_core.closest_surface_point_transfer()``: for each gap
    target vertex, find the closest point on the mesh's own surface to its
    flipped (source-side) position, and barycentric-blend that triangle's 3
    vertices' *pre-mirror* weight data (id-remapped src->tgt via id_pairs).
    A location with genuinely no mirrored-bone weight nearby (e.g. a
    Spine-only area incorrectly flagged as a gap) blends to nothing and is
    left untouched — see the Rust-side gap detection comment.

    *surface* must be a **source-side-only** surface (see
    ``build_source_side_surface``) — a whole-mesh surface can bleed weight
    from the target side's own geometry when the mesh self-intersects.
    """
    if not gap_v_indices or surface is None:
        return

    bvh, triangles, positions = surface
    touched = []
    for v_idx in gap_v_indices:
        flipped = _flip_point(vertex_coords[v_idx], axis_idx)
        location, _normal, tri_idx, _dist = bvh.find_nearest(flipped)
        if tri_idx is None:
            continue

        tri = triangles[tri_idx]
        bary = poly_3d_calc([positions[i] for i in tri], location)

        bone_weights = {}
        for w, src_v in zip(bary, tri):
            for src_id, bw in layer_dict_before.get(src_v, {}).items():
                tgt_id = id_pairs.get(src_id)
                if tgt_id is None:
                    continue
                bone_weights[tgt_id] = bone_weights.get(tgt_id, 0.0) + w * bw

        if not bone_weights:
            continue

        bucket = result.setdefault(v_idx, {})
        for tgt_id, w in bone_weights.items():
            bucket[tgt_id] = bucket.get(tgt_id, 0.0) + w
        touched.append(v_idx)

    if not touched:
        return

    rust = CoreFacade.get_rust_gateway("norm_all_unlocked")
    for v_idx in touched:
        v_weights = result.get(v_idx)
        if not v_weights:
            continue
        result[v_idx] = dict(rust.call("rust_norm_all_unlocked", v_weights, vertex_groups_lock))


def _fill_mask_gaps(mask_dict_before, result, gap_v_indices, vertex_coords, axis_idx, surface):
    """BVH + barycentric fallback for the mask channel's gaps.

    Missing-vertex fallback default is ``1.0`` (a "filled white" layer has
    no dense per-vertex mask entries), matching the confirmed-correct
    convention in ``docs/bug-history/0023`` rather than a bare ``0.0``.

    *surface* must be a **source-side-only** surface — see
    ``_fill_weight_gaps``'s note on why a whole-mesh surface can bleed data
    from the target side's own geometry when the mesh self-intersects.
    """
    if not gap_v_indices or surface is None:
        return

    bvh, triangles, positions = surface
    for v_idx in gap_v_indices:
        flipped = _flip_point(vertex_coords[v_idx], axis_idx)
        location, _normal, tri_idx, _dist = bvh.find_nearest(flipped)
        if tri_idx is None:
            continue

        tri = triangles[tri_idx]
        bary = poly_3d_calc([positions[i] for i in tri], location)
        mask_val = sum(w * mask_dict_before.get(src_v, 1.0) for w, src_v in zip(bary, tri))
        if mask_val > 0.0:
            result[v_idx] = mask_val


def check_self_intersection(core_facade, axis_idx, surface, ignore_zone=1e-4):
    """Detect whether the mesh's own geometry already crosses the mirror
    plane into where its mirrored copy will sit (e.g. an oversized pant leg
    that intersects the opposite leg before any mirroring happens).

    This is purely a rest-pose geometry check — independent of weight data
    — using ``mathutils.bvhtree.BVHTree.overlap()`` against a flipped copy
    of the same surface. Detection only: never blocks or alters the mirror,
    the caller only warns.

    Returns the set of vertex indices (in the *original*, unflipped mesh)
    involved in an out-of-band overlap. Overlaps confined to the centerline
    seam itself (within ``ignore_zone`` of the mirror plane) are excluded,
    since a correctly-built symmetric mesh's own seam triangles are
    expected to touch their mirrored copy there by construction.
    """
    bvh, triangles, positions = surface
    flipped_positions = [_flip_point(p, axis_idx) for p in positions]
    bvh_flipped = BVHTree.FromPolygons(flipped_positions, triangles, all_triangles=True)

    overlaps = bvh.overlap(bvh_flipped)
    if not overlaps:
        return set()

    hit_verts = set()
    for tri_a_idx, tri_b_idx in overlaps:
        tri_a = triangles[tri_a_idx]
        tri_b = triangles[tri_b_idx]
        if all(abs(positions[i][axis_idx]) <= ignore_zone for i in tri_a) and \
           all(abs(positions[i][axis_idx]) <= ignore_zone for i in tri_b):
            continue
        hit_verts.update(tri_a)
        hit_verts.update(tri_b)

    return hit_verts


def build_layer_mirror_plan(core_facade, axis, direction, sr_raw):
    """Resolve VG name pairs -> int ID pairs for the mirror computation.

    Returns None when no matching pairs exist (caller skips the layer channel).
    """
    vg_names = [vg.name for vg in core_facade.get_vertex_groups()]
    bone_centers = get_bone_centers(core_facade)
    CoreFacade.debug_log(
        "feature_domains",
        f"mirror.build_layer_mirror_plan(): sr_raw={sr_raw!r} "
        f"vg_names_sample={vg_names[:10]!r}",
    )
    name_pairs = generate_pairs(
        vg_names=vg_names,
        bone_centers=bone_centers,
        sr_list=sr_raw,
        axis=axis,
        direction=direction,
    )
    CoreFacade.debug_log(
        "feature_domains",
        f"mirror.build_layer_mirror_plan(): vg_names={len(vg_names)} "
        f"bone_centers={len(bone_centers)} name_pairs={name_pairs}",
    )

    # Cross-check: for every identity (unmatched) pair, redo the *.l -> *.r
    # style replace in plain Python and check byte-exact presence in
    # vg_names. Surfaces case/whitespace/naming mismatches invisible from
    # the Rust-side result alone.
    vg_name_set = set(vg_names)
    for src, tgt in name_pairs.items():
        if src != tgt:
            continue
        for search_text, replace_text in sr_raw:
            if not search_text or not replace_text or '*' not in search_text:
                continue
            if search_text.replace('*', '') not in src:
                continue
            candidate = src.replace(search_text.replace('*', ''), replace_text.replace('*', ''))
            CoreFacade.debug_log(
                "feature_domains",
                f"mirror.build_layer_mirror_plan(): identity-pair check src={src!r} "
                f"rule=({search_text!r},{replace_text!r}) candidate={candidate!r} "
                f"present_in_vg_names={candidate in vg_name_set}",
            )

    if not name_pairs:
        return None

    bone_to_id, id_to_bone = core_facade.get_unified_mapping()
    id_pairs = {
        bone_to_id[src]: bone_to_id[tgt]
        for src, tgt in name_pairs.items()
        if src in bone_to_id and tgt in bone_to_id
    }
    CoreFacade.debug_log(
        "feature_domains",
        f"mirror.build_layer_mirror_plan(): id_pairs={id_pairs}",
    )
    return id_pairs if id_pairs else None


def execute_mirror_pipeline(core_facade):
    """Full mirror pipeline via CoreFacade only — no UIController dependency.

    Raises ValueError when neither channel can produce output, allowing the
    domain to return CANCELLED without an unhandled exception.
    """
    from .mirror_feature import MirrorPreferencesService

    axis = MirrorPreferencesService.get_mirror_axis()
    direction = MirrorPreferencesService.get_mirror_direction()
    sr_raw = MirrorPreferencesService.get_mirror_search_replace_pairs()
    is_mask = core_facade.is_mask_context()
    both_data = MirrorPreferencesService.get_mirror_both_data()
    fill_gaps = MirrorPreferencesService.get_mirror_fill_gaps()
    warn_intersection = MirrorPreferencesService.get_mirror_warn_self_intersection()
    axis_idx = _AXIS_IDX[axis]

    do_mask = is_mask or both_data
    do_layer = (not is_mask) or both_data

    CoreFacade.debug_log(
        "feature_domains",
        f"mirror.execute_mirror_pipeline(): is_mask={is_mask} both_data={both_data} "
        f"do_mask={do_mask} do_layer={do_layer} obj.mode={core_facade.get_obj().mode} "
        f"axis={axis} direction={direction} fill_gaps={fill_gaps} "
        f"warn_intersection={warn_intersection}",
    )

    # Topology-based side classification (see module docstring's
    # "TOPOLOGY-BASED SIDE CLASSIFICATION") — computed once and shared by
    # both channels below AND the gap-fill fallback's source-side surface,
    # since a self-intersecting mesh needs the SAME side assignment
    # everywhere or the channels would disagree on which vertex is which side.
    target_side_mask = classify_sides_by_topology(core_facade, axis_idx, direction)

    # check_self_intersection needs BOTH sides of the surface (that's the whole
    # point — detecting where they cross). The gap-fill fallback below must
    # instead use a SOURCE-SIDE-ONLY surface, or a self-intersecting mesh
    # bleeds weight from the target side's own geometry into the fallback
    # (confirmed: caused a visible "spiky" weight artifact on an intersecting
    # model) — these are two different BVHs, never reuse one for the other.
    intersect_surface = build_local_surface(core_facade) if warn_intersection else None
    fill_surface = (
        build_source_side_surface(core_facade, target_side_mask) if fill_gaps else None
    )

    if warn_intersection:
        hit_verts = check_self_intersection(core_facade, axis_idx, intersect_surface)
        if hit_verts:
            core_facade.show_toast(
                f"Mirror: {len(hit_verts)} vertex(es) already cross the mirror "
                "plane before mirroring — check for oversized geometry."
            )
            CoreFacade.debug_log(
                "feature_domains",
                f"mirror.execute_mirror_pipeline(): self-intersection pre-flight "
                f"found {len(hit_verts)} vertex(es): {sorted(hit_verts)[:20]!r}",
            )

    if do_layer:
        id_pairs = build_layer_mirror_plan(core_facade, axis, direction, sr_raw)
        if id_pairs is None:
            do_layer = False
            CoreFacade.debug_log(
                "feature_domains",
                "mirror.execute_mirror_pipeline(): id_pairs is None -> do_layer disabled",
            )

    if not do_mask and not do_layer:
        raise ValueError("No mirror pairs found for either channel.")

    if do_mask:
        mask_dict = core_facade.get_active_mask_dict()
        vertex_coords = core_facade.get_vertex_coordinates()
        res_mask, mask_gaps = apply_mask_flat(
            mask_dict=mask_dict,
            vertex_coords=vertex_coords,
            target_side_mask=target_side_mask,
            axis=axis,
            direction=direction,
            num_verts=core_facade.get_num_verts(),
        )
        if fill_gaps and mask_gaps:
            _fill_mask_gaps(mask_dict, res_mask, mask_gaps, vertex_coords, axis_idx, fill_surface)
            CoreFacade.debug_log(
                "feature_domains",
                f"mirror.execute_mirror_pipeline(): mask gap-fill covered "
                f"{len(mask_gaps)} candidate vertex(es)",
            )
        core_facade.write_mask_dict(res_mask)

    if do_layer:
        # read_active_layer() caches the unified mapping for the write call.
        layer_str = core_facade.read_active_layer()
        bone_to_id, id_to_bone = core_facade.get_unified_mapping()

        layer_int = {
            int(v_idx): {
                int(bone_to_id[b]): float(w)
                for b, w in weights.items()
                if b in bone_to_id
            }
            for v_idx, weights in layer_str.items()
        }
        locks_by_id = core_facade.get_locks_by_id()
        CoreFacade.debug_log(
            "feature_domains",
            f"mirror.execute_mirror_pipeline(): layer_int verts={len(layer_int)} "
            f"id_pairs={id_pairs} locks_by_id={locks_by_id}",
        )
        vertex_coords = core_facade.get_vertex_coordinates()
        res_layer_int, weight_gaps = apply(
            layer_dict=layer_int,
            id_pairs=id_pairs,
            vertex_groups_lock=locks_by_id,
            vertex_coords=vertex_coords,
            target_side_mask=target_side_mask,
            axis=axis,
            direction=direction,
        )
        if fill_gaps and weight_gaps:
            _fill_weight_gaps(
                layer_int, res_layer_int, weight_gaps, id_pairs,
                vertex_coords, axis_idx, fill_surface, locks_by_id,
            )
            CoreFacade.debug_log(
                "feature_domains",
                f"mirror.execute_mirror_pipeline(): weight gap-fill covered "
                f"{len(weight_gaps)} candidate vertex(es)",
            )
        changed_verts = sum(
            1 for v_idx, w in res_layer_int.items() if w != layer_int.get(v_idx)
        )
        CoreFacade.debug_log(
            "feature_domains",
            f"mirror.execute_mirror_pipeline(): res_layer_int verts={len(res_layer_int)} "
            f"changed_verts={changed_verts}",
        )
        res_layer_str = {
            int(v_idx): {
                str(id_to_bone[b_id]): float(w)
                for b_id, w in weights.items()
                if b_id in id_to_bone
            }
            for v_idx, weights in res_layer_int.items()
        }
        # write_active_layer calls finish() internally — no explicit finish needed.
        core_facade.write_active_layer(res_layer_str)
        CoreFacade.debug_log(
            "feature_domains",
            f"mirror.execute_mirror_pipeline(): write_active_layer() done, "
            f"res_layer_str verts={len(res_layer_str)}",
        )
    else:
        # Mask-only path: write_mask_dict does not call finish.
        core_facade.finish_color_only()
