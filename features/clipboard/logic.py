# Copyright (c) 2026 Natchapon Srisuk. All rights reserved.
from __future__ import annotations
from ...core.facade import CoreFacade as _CoreFacade
data_ops = _CoreFacade.get_clipboard_data_ops()

# ═════════════════════════════════════════════════════════════════════════
#  🌟 NEW: MANUAL DATA PIPELINE (ทำงานตาม Enum สั่ง ไม่สนบริบทหน้าจอ)
# ═════════════════════════════════════════════════════════════════════════

def copy_data_manual(ctrl, action: str = 'COPY') -> dict:
    """สั่งคัดลอก/ตัดข้อมูลแมนนวล บังคับสลับชั้น Custom Properties ตาม Enum UI"""
    clip_mgr = _clipboard_manager
    selected = ctrl._selected_verts()
    all_verts_count = len(ctrl.mesh.vertices)
    
    # สกัดข้อมูลโดยตรงจาก WindowManager Enum
    prefs = ctrl.context.window_manager.superskin_clipboard_prefs
    force_mask = (prefs.target_data_type == 'LAYER')

    if len(selected) == 0 or len(selected) == all_verts_count:
        if force_mask:
            mask_dict = ctrl.storage.read_active_mask_dict()
            subset = {str(k): v for k, v in mask_dict.items()}
        else:
            layer_dict = ctrl.storage.read_active_layer_dict()
            subset = {str(k): dict(w) for k, w in layer_dict.items()}
    else:
        if force_mask:
            mask_dict = ctrl.storage.read_active_mask_dict()
            subset = data_ops.extract_mask_subset(mask_dict, selected)
        else:
            layer_dict = ctrl.storage.read_active_layer_dict()
            subset = data_ops.extract_weight_subset(layer_dict, selected)

    if not subset:
        raise ValueError("Nothing to capture — Selected target has no active weights.")

    kind = 'MASK' if force_mask else 'WEIGHT'
    clip_mgr.set_clipboard(kind, subset, ctrl.mesh.name)

    if action == 'CUT':
        if len(selected) == 0 or len(selected) == all_verts_count:
            if force_mask:
                ctrl.storage.write_mask_dict(ctrl.active_layer_index, {})
            else:
                ctrl.storage.write_layer_dict(ctrl.active_layer_index, {})
        else:
            sel_set = {int(v) for v in selected}
            if force_mask:
                mask_dict = ctrl.storage.read_active_mask_dict()
                remaining = {int(k): w for k, w in mask_dict.items() if int(k) not in sel_set}
                ctrl.storage.write_mask_dict(ctrl.active_layer_index, remaining)
            else:
                layer_dict = ctrl.storage.read_active_layer_dict()
                remaining = {int(k): dict(w) for k, w in layer_dict.items() if int(k) not in sel_set}
                ctrl.storage.write_layer_dict(ctrl.active_layer_index, remaining)
        ctrl._finish(color_only=False)

    return clip_mgr.get_clipboard()


def paste_data_manual(ctrl, mode: str = 'REPLACE') -> dict:
    """สั่งวางข้อมูลแมนนวล ดัดแปลงค่าน้ำหนักปลายทางอิงตาม Enum 100%"""
    clip_mgr = _clipboard_manager
    if not clip_mgr.has_clipboard():
        raise ValueError("Clipboard is empty — copy or cut first")

    clip = clip_mgr.get_clipboard()
    clip_data = clip["data"]
    clip_kind = clip["kind"]
    source_mesh_name = clip["source_mesh"]

    # บังคับประเภทข้อมูลปลายทางจาก Enum เสมอ
    prefs = ctrl.context.window_manager.superskin_clipboard_prefs
    force_mask_target = (prefs.target_data_type == 'LAYER')
    
    target_verts = ctrl._selected_verts()
    if len(target_verts) == 0:
        target_verts = list(range(len(ctrl.mesh.vertices)))

    target_vg_names = {vg.name for vg in ctrl.obj.vertex_groups}
    ok, reason = data_ops.validate_bone_compatibility(clip_data, target_vg_names, clip_kind)
    if not ok:
        raise ValueError(reason)

    paste_kind = clip_kind
    paste_data = clip_data

    # ทำการแปลงโครงสร้างค่าน้ำหนักข้ามโหมดหากความต้องการประเภทไม่ตรงกับคลิปบอร์ด
    if clip_kind == 'WEIGHT' and force_mask_target:
        paste_kind = 'MASK'
        paste_data = _convert_weight_to_mask(paste_data, ctrl)
    elif clip_kind == 'MASK' and not force_mask_target:
        paste_kind = 'WEIGHT'
        paste_data = _convert_mask_to_weight(paste_data, ctrl)

    current_mesh_name = ctrl.mesh.name
    if paste_kind == 'WEIGHT':
        resolved = data_ops.resolve_paste_targets_weight(paste_data, target_verts, source_mesh_name, current_mesh_name)
        _merge_weight_paste(ctrl, resolved, mode)
    else:
        resolved = data_ops.resolve_paste_targets_mask(paste_data, target_verts, source_mesh_name, current_mesh_name)
        _merge_mask_paste(ctrl, resolved, mode)

    ctrl._finish(color_only=False)
    return {"status": "FINISHED"}


# ═════════════════════════════════════════════════════════════════════════
#  🔄 AUTOMATIC PIPELINE (ดั้งเดิม คุมความฉลาดของฝั่ง Vertex ส่วนล่าง)
# ═════════════════════════════════════════════════════════════════════════

class ClipboardManager:
    def __init__(self):
        self._clip = None

    def has_clipboard(self) -> bool:
        return self._clip is not None and "data" in self._clip and bool(self._clip["data"])

    def get_clipboard(self) -> dict:
        if not self.has_clipboard():
            raise ValueError("Clipboard is empty — copy or cut first")
        return self._clip

    def set_clipboard(self, kind: str, data: dict, source_mesh: str):
        self._clip = {"kind": kind, "data": data, "source_mesh": source_mesh}

    def clear_clipboard(self):
        self._clip = None

_clipboard_manager = ClipboardManager()

def copy(ctrl) -> dict:
    clip_mgr = _clipboard_manager
    all_verts_count = len(ctrl.mesh.vertices)
    selected = ctrl._selected_verts()
    is_mask = ctrl._is_mask_context()

    if len(selected) == 0 or len(selected) == all_verts_count:
        if is_mask:
            mask_dict = ctrl.storage.read_active_mask_dict()
            subset = {str(k): v for k, v in mask_dict.items()}
        else:
            layer_dict = ctrl.storage.read_active_layer_dict()
            subset = {str(k): dict(w) for k, w in layer_dict.items()}
    else:
        if is_mask:
            mask_dict = ctrl.storage.read_active_mask_dict()
            subset = data_ops.extract_mask_subset(mask_dict, selected)
        else:
            layer_dict = ctrl.storage.read_active_layer_dict()
            subset = data_ops.extract_weight_subset(layer_dict, selected)

    if not subset:
        raise ValueError("Nothing to copy — selected vertices have no data.")

    kind = 'MASK' if is_mask else 'WEIGHT'
    clip_mgr.set_clipboard(kind, subset, ctrl.mesh.name)
    return clip_mgr.get_clipboard()

def cut(ctrl) -> dict:
    clip = copy(ctrl)
    is_mask = ctrl._is_mask_context()
    all_verts_count = len(ctrl.mesh.vertices)
    selected = ctrl._selected_verts()

    if len(selected) == 0 or len(selected) == all_verts_count:
        if is_mask:
            ctrl.storage.write_mask_dict(ctrl.active_layer_index, {})
        else:
            ctrl.storage.write_layer_dict(ctrl.active_layer_index, {})
    else:
        sel_set = {int(v) for v in selected}
        if is_mask:
            mask_dict = ctrl.storage.read_active_mask_dict()
            remaining = {int(k): w for k, w in mask_dict.items() if int(k) not in sel_set}
            ctrl.storage.write_mask_dict(ctrl.active_layer_index, remaining)
        else:
            layer_dict = ctrl.storage.read_active_layer_dict()
            remaining = {int(k): dict(w) for k, w in layer_dict.items() if int(k) not in sel_set}
            ctrl.storage.write_layer_dict(ctrl.active_layer_index, remaining)

    ctrl._finish(color_only=False)
    return clip

def paste(ctrl, mode: str = 'REPLACE') -> dict:
    clip_mgr = _clipboard_manager
    if not clip_mgr.has_clipboard():
        raise ValueError("Clipboard is empty — copy or cut first")

    clip = clip_mgr.get_clipboard()
    clip_data = clip["data"]
    clip_kind = clip["kind"]
    source_mesh_name = clip["source_mesh"]

    all_verts_count = len(ctrl.mesh.vertices)
    selected_targets = ctrl._selected_verts()
    target_verts = selected_targets if len(selected_targets) > 0 else list(range(all_verts_count))

    target_vg_names = {vg.name for vg in ctrl.obj.vertex_groups}
    ok, reason = data_ops.validate_bone_compatibility(clip_data, target_vg_names, clip_kind)
    if not ok:
        raise ValueError(reason)

    is_mask_target = ctrl._is_mask_context()
    paste_kind = clip_kind
    paste_data = clip_data

    if clip_kind == 'WEIGHT' and is_mask_target:
        paste_kind = 'MASK'
        paste_data = _convert_weight_to_mask(paste_data, ctrl)
    elif clip_kind == 'MASK' and not is_mask_target:
        paste_kind = 'WEIGHT'
        paste_data = _convert_mask_to_weight(paste_data, ctrl)

    current_mesh_name = ctrl.mesh.name
    if paste_kind == 'WEIGHT':
        resolved = data_ops.resolve_paste_targets_weight(paste_data, target_verts, source_mesh_name, current_mesh_name)
    else:
        resolved = data_ops.resolve_paste_targets_mask(paste_data, target_verts, source_mesh_name, current_mesh_name)

    if paste_kind == 'WEIGHT':
        _merge_weight_paste(ctrl, resolved, mode)
    else:
        _merge_mask_paste(ctrl, resolved, mode)

    ctrl._finish(color_only=False)
    return {"status": "FINISHED"}

def select_affected(ctrl) -> set:
    if ctrl._is_mask_context():
        mask_dict = ctrl.storage.read_active_mask_dict()
        return data_ops.vertices_with_mask_override(mask_dict)
    active_id = ctrl._active_vg_id()
    if active_id is None:
        raise ValueError("No active Vertex Group selected")
    active_name = ctrl.obj.vertex_groups[active_id].name
    layer_dict = ctrl.storage.read_active_layer_dict()
    return data_ops.vertices_with_weight(layer_dict, active_name)

def _convert_weight_to_mask(weight_data: dict, ctrl) -> dict:
    active_vg_id = ctrl._active_vg_id()
    id_to_name = ctrl._idx_to_name()
    active_bone_name = id_to_name.get(active_vg_id, "") if active_vg_id is not None else ""
    result: dict = {}
    for v, weights in weight_data.items():
        result[v] = weights.get(active_bone_name, 0.0)
    return result

def _convert_mask_to_weight(mask_data: dict, ctrl) -> dict:
    active_vg_id = ctrl._active_vg_id()
    if active_vg_id is None:
        raise ValueError("No active Vertex Group selected for conversion")
    id_to_name = ctrl._idx_to_name()
    active_bone_name = id_to_name.get(active_vg_id, "")
    result: dict = {}
    for v, val in mask_data.items():
        result[v] = {active_bone_name: float(val)}
    return result

def _merge_weight_paste(ctrl, resolved: dict[int, dict[str, float]], mode: str = 'REPLACE'):
    layer_dict = {int(k): v for k, v in ctrl.storage.read_active_layer_dict().items()}
    for v_int, bone_weights in resolved.items():
        if mode == 'REPLACE':
            layer_dict[v_int] = {bone_name: float(w) for bone_name, w in bone_weights.items()}
        else:
            if v_int not in layer_dict: layer_dict[v_int] = {}
            existing = layer_dict[v_int]
            for bone_name, w in bone_weights.items():
                current = existing.get(bone_name, 0.0)
                if mode == 'ADD': existing[bone_name] = min(1.0, current + float(w))
                elif mode == 'SUBTRACT': existing[bone_name] = max(0.0, current - float(w))
    ctrl.storage.write_layer_dict(ctrl.active_layer_index, layer_dict)

def _merge_mask_paste(ctrl, resolved: dict[int, float], mode: str = 'REPLACE'):
    mask_dict = {int(k): v for k, v in ctrl.storage.read_active_mask_dict().items()}
    for v_int, val in resolved.items():
        if mode == 'REPLACE':
            mask_dict[v_int] = float(val)
        else:
            current = float(mask_dict.get(v_int, 0.0))
            if mode == 'ADD': mask_dict[v_int] = min(1.0, current + float(val))
            elif mode == 'SUBTRACT': mask_dict[v_int] = max(0.0, current - float(val))
    ctrl.storage.write_mask_dict(ctrl.active_layer_index, mask_dict)