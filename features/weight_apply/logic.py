"""Weight-apply logic — Rust Accelerated Multi-OS Portal.

Merged from simple_ops_logic.py and smooth_logic.py.
Contains normalization helpers plus add, scale, sharpen, and smooth operations.

All functions operate on Integer Bone IDs. UIController guarantees int-keyed
dicts before these functions are invoked.
"""

from collections import deque

from ...core.facade import CoreFacade


# ═══════════════════════════════════════════════════════════════════════════
#  Normalization helpers
# ═══════════════════════════════════════════════════════════════════════════

def _call_norm_rust(gateway_tag: str, fn_name: str, v_weights, *args):
    """Call a Rust normalization function and update *v_weights* in-place with the result."""
    rust = CoreFacade.get_rust_gateway(gateway_tag)
    result = rust.call(fn_name, v_weights, *args)
    v_weights.clear()
    v_weights.update(result)
    return v_weights


def normalize_around_active(v_weights, active_vg_id, locks, active_layer_idx=0):
    """Normalize so unlocked weights sum to 1.0 - lock_total using Integer Bone IDs.

    Args:
        v_weights: ``{bone_id: float}`` — mutable, updated in-place.
        active_vg_id: the integer bone ID that was just changed.
        locks: ``{bone_id: bool}`` — True when the group is locked.
        active_layer_idx: layer index (0 = base).
    """
    return _call_norm_rust(
        "norm_around_active",
        "rust_norm_around_active",
        v_weights,
        active_vg_id,
        locks,
        active_layer_idx,
    )


def normalize_all_unlocked(v_weights, locks):
    """Scale every unlocked weight proportionally so they sum to 1.0 - lock_total."""
    return _call_norm_rust("norm_all_unlocked", "rust_norm_all_unlocked", v_weights, locks)


# ═══════════════════════════════════════════════════════════════════════════
#  Add
# ═══════════════════════════════════════════════════════════════════════════

def apply_add(layer_dict, mask_dict, selected_verts, active_vg_id, intensity,
              vertex_groups_lock, active_layer_idx, is_mask_mode):
    """Add weight to the active bone on selected vertices using Integer Bone IDs."""
    rust = CoreFacade.get_rust_gateway("add_logic")
    return rust.call(
        "rust_add_logic",
        layer_dict,
        mask_dict,
        selected_verts,
        active_vg_id,
        intensity,
        vertex_groups_lock,
        active_layer_idx,
        is_mask_mode,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Scale
# ═══════════════════════════════════════════════════════════════════════════

def apply_scale(layer_dict, mask_dict, selected_verts, active_vg_id, intensity,
                vertex_groups_lock, is_mask_mode):
    """Scale the active bone weight on selected vertices using Integer Bone IDs."""
    rust = CoreFacade.get_rust_gateway("scale_logic")
    return rust.call(
        "rust_scale_logic",
        layer_dict,
        mask_dict,
        selected_verts,
        active_vg_id,
        intensity,
        vertex_groups_lock,
        is_mask_mode,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Sharpen
# ═══════════════════════════════════════════════════════════════════════════

def apply_sharpen(layer_dict, mask_dict, selected_verts, neighbors, active_vg_id,
                  intensity, is_mask_mode):
    """Sharpen the active bone weight on selected vertices using Integer Bone IDs."""
    rust = CoreFacade.get_rust_gateway("sharpen_logic")
    return rust.call(
        "rust_sharpen_logic",
        layer_dict,
        mask_dict,
        selected_verts,
        neighbors,
        active_vg_id,
        intensity,
        is_mask_mode,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Smooth
# ═══════════════════════════════════════════════════════════════════════════

def apply_smooth(layer_dict, mask_dict, selected_verts, neighbors, intensity,
                 vertex_groups_lock, affected_only, is_mask_mode):
    """Smooth weights across neighbouring vertices with Integer Bone ID core stability."""
    rust = CoreFacade.get_rust_gateway("smooth_logic")
    return rust.call(
        "rust_smooth_logic",
        layer_dict, mask_dict, selected_verts, neighbors,
        intensity, vertex_groups_lock, affected_only, is_mask_mode,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Smooth Across Surface — geodesic-radius neighbor expansion
# ═══════════════════════════════════════════════════════════════════════════
#
# Plain 1-ring adjacency (`get_cached_mesh_neighbors()`) ties the smoothing
# neighborhood to hop count, which makes the effective real-world smoothing
# radius vary with local topology density. This module builds an alternate
# neighbor map keyed by an approximate surface (geodesic) distance instead,
# so the same call to `rust_smooth_logic` averages over a comparable
# real-world radius on both dense and sparse regions of the mesh. No Rust/
# core code is touched — this only changes what is passed as `neighbors`.

_SURFACE_CACHE: dict = {}
_SURFACE_CACHE_MAX_MESHES = 8


def _mesh_cache_key(core_facade, radius_multiplier, max_hops):
    """Identity key for the current mesh + radius settings, used to invalidate
    the per-vertex cache. Radius/hop settings are part of the key because
    different callers (smooth vs. sharpen) request different neighborhood
    sizes for the same mesh."""
    mesh = core_facade.get_mesh()
    return (mesh.as_pointer(), core_facade.get_num_verts(), radius_multiplier, max_hops)


def _local_radius(v_idx, coords, adjacency, radius_multiplier):
    """Approximate a physical smoothing radius from the average 1-ring edge length."""
    ring = adjacency.get(v_idx)
    if not ring:
        return 0.0
    cx, cy, cz = coords[v_idx]
    total = 0.0
    for n in ring:
        nx, ny, nz = coords[n]
        total += ((nx - cx) ** 2 + (ny - cy) ** 2 + (nz - cz) ** 2) ** 0.5
    return (total / len(ring)) * radius_multiplier


def _bfs_within_radius(v_idx, coords, adjacency, radius, max_hops):
    """Walk the 1-ring adjacency graph, accumulating edge length as an approximate
    geodesic distance, and collect every vertex reachable within *radius*."""
    visited = {v_idx: 0.0}
    queue = deque([(v_idx, 0.0, 0)])
    result = []
    while queue:
        cur, dist, hops = queue.popleft()
        if cur != v_idx:
            result.append(cur)
        if hops >= max_hops:
            continue
        cx, cy, cz = coords[cur]
        for nb in adjacency.get(cur, ()):
            nx, ny, nz = coords[nb]
            edge_len = ((nx - cx) ** 2 + (ny - cy) ** 2 + (nz - cz) ** 2) ** 0.5
            new_dist = dist + edge_len
            if new_dist > radius:
                continue
            if nb in visited and visited[nb] <= new_dist:
                continue
            visited[nb] = new_dist
            queue.append((nb, new_dist, hops + 1))
    return result


def build_surface_neighbors(core_facade, target_verts, radius_multiplier=3.0, max_hops=8):
    """Build a `{v_idx: [neighbor_idx, ...]}` map sized by surface distance rather
    than hop count, in the same shape `rust_smooth_logic` already expects for its
    `neighbors` argument. Results are cached per vertex for the lifetime of the
    current mesh identity, since the map only depends on topology/coordinates.
    """
    key = _mesh_cache_key(core_facade, radius_multiplier, max_hops)
    if key not in _SURFACE_CACHE and len(_SURFACE_CACHE) >= _SURFACE_CACHE_MAX_MESHES:
        _SURFACE_CACHE.clear()
    cache = _SURFACE_CACHE.setdefault(key, {})

    missing = [v for v in target_verts if v not in cache]
    if missing:
        coords = core_facade.get_vertex_coordinates()
        adjacency = core_facade.get_cached_mesh_neighbors()
        for v in missing:
            radius = _local_radius(v, coords, adjacency, radius_multiplier)
            cache[v] = (
                _bfs_within_radius(v, coords, adjacency, radius, max_hops)
                if radius > 0 else list(adjacency.get(v, ()))
            )

    return {v: cache[v] for v in target_verts}


# Sharpen's contrast formula (`new = current + (current - avg(neighbors)) *
# intensity`, in `rust_sharpen_logic`) amplifies the difference between a
# vertex and its neighbor average. Fed with plain 1-ring adjacency (often
# only 4-6 vertices), a single neighbor that clamps to 0.0/1.0 dominates that
# average, so the next press pushes its still-unsaturated neighbors hard in
# the opposite direction — a checkerboard-style divergence that reads as
# isolated per-vertex spikes instead of a cohesive ring/zone. Widening the
# averaging neighborhood dilutes any single saturated vertex's influence and
# keeps the contrast reference representative of the surrounding zone.
SHARPEN_RADIUS_MULTIPLIER = 2.0
