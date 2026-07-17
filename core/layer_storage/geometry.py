"""Mesh-geometry harvesting helpers.

Pure geometry operations — no custom-property I/O, no data encoding.
All functions accept an explicit mesh/obj parameter (no ``self.mesh``).
"""

import bmesh
from mathutils.bvhtree import BVHTree


def get_local_mapping(obj) -> tuple[dict[str, int], dict[int, str]]:
    """Generates two-way fast-lookup tables for runtime mapping (O(1)).

    Returns:
        (bone_to_id, id_to_bone) where:
        - bone_to_id: ``{vg_name: vg_index}``
        - id_to_bone: ``{vg_index: vg_name}``
    """
    bone_to_id = {vg.name: vg.index for vg in obj.vertex_groups
                  if not vg.name.startswith("__ssp_")}
    id_to_bone = {vg.index: vg.name for vg in obj.vertex_groups
                  if not vg.name.startswith("__ssp_")}
    return bone_to_id, id_to_bone


def get_unified_mapping(obj) -> tuple[dict[str, int], dict[int, str]]:
    """Like get_local_mapping but also assigns synthetic int IDs to orphaned
    bones (in superskin_bones_collection but not in vertex_groups), so
    downstream code treats real and orphaned bones identically.

    The synthetic ID sequence MUST start right after the real (non-__ssp_*)
    vertex-group count, not len(obj.vertex_groups) -- while Edit Mode temp
    VGs are loaded, obj.vertex_groups also holds one __ssp_N per bone (real
    and orphan) plus __ssp_m/__ssp_meta, so len(obj.vertex_groups) is
    roughly double the real count. Using that inflated count here reassigns
    an orphan a DIFFERENT synthetic ID on every fresh call made while temp
    VGs exist than the ID baked into its __ssp_N VG's name back when
    load_layer_to_temp_vgs() created it (before this session's temp VGs
    existed, when len(vertex_groups) was still just the real count). Once
    that mismatch happens, write_layer_to_temp_vgs_bm()'s VG-name lookup
    (id_to_bone.get(int(suffix))) silently fails to resolve the orphan's
    real __ssp_N VG at all, so it's invisible to that write path's
    clear-if-absent loop and its weight can never be reduced or cleared no
    matter what gets computed -- using len(bone_to_id) here instead keeps
    the sequence anchored to the real count alone, identical whether or
    not temp VGs currently exist.
    """
    bone_to_id = {vg.name: vg.index for vg in obj.vertex_groups
                  if not vg.name.startswith("__ssp_")}
    id_to_bone = {vg.index: vg.name for vg in obj.vertex_groups
                  if not vg.name.startswith("__ssp_")}
    synthetic_id = len(bone_to_id)
    for item in getattr(obj, 'superskin_bones_collection', ()):
        if item.is_orphan and item.name not in bone_to_id:
            bone_to_id[item.name] = synthetic_id
            id_to_bone[synthetic_id] = item.name
            synthetic_id += 1
    return bone_to_id, id_to_bone


def build_mesh_neighbors(mesh) -> dict:
    """Build raw mesh topology map.

    Keeps pure Python types {int: set(int)} for internal decoupling.
    """
    neighbors = {}
    for edge in mesh.edges:
        v0, v1 = edge.vertices
        neighbors.setdefault(v0, set()).add(v1)
        neighbors.setdefault(v1, set()).add(v0)
    return neighbors


def collect_mesh_weights(mesh, vert_indices: set) -> dict:
    """Collect mesh-level weights for *vert_indices*.

    Returns ``{v_idx: {vg_idx: weight}}``.
    """
    result = {}
    for v_idx in vert_indices:
        vw = {}
        for g in mesh.vertices[v_idx].groups:
            vw[g.group] = g.weight
        if vw:
            result[v_idx] = vw
    return result


def get_vertex_coordinates(mesh) -> list:
    """Return ``[(x, y, z), ...]`` for every mesh vertex (local space)."""
    return [(v.co.x, v.co.y, v.co.z) for v in mesh.vertices]


def build_bvh_tree(mesh):
    """Triangulate the mesh and return a BVHTree from its bmesh."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    return bvh
