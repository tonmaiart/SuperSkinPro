import bpy
import json
import os
from bpy_extras.io_utils import ExportHelper, ImportHelper


class WM_OT_superskin_export_json(bpy.types.Operator, ExportHelper):
    bl_idname = "superskin.export_weight_json"
    bl_label = "Export Weights to JSON"
    bl_options = {'REGISTER', 'UNDO'}
    
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(
        default="*.json",
        options={'HIDDEN'}
    )

    def execute(self, context):
        """Export ALL layers (weights, masks, metadata) to JSON file."""
        from ...core.facade import CoreFacade
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No active mesh object")
            return {'CANCELLED'}
        
        facade = CoreFacade(context)
        
        # Get all layer data
        meta_list = facade.get_meta_list()
        active_index = facade.get_active_layer_index()
        
        if not meta_list:
            self.report({'WARNING'}, "No layers to export")
            return {'CANCELLED'}
        
        # Get precision from preferences
        wm = context.window_manager
        prefs = getattr(wm, "superskin_data_io_prefs", None)
        precision = prefs.export_precision if prefs else 5
        
        # Build export data structure
        export_data = {
            "version": 1,
            "active_layer_index": active_index,
            "layers": []
        }
        
        # Export each layer
        for layer_meta in meta_list:
            slot_index = layer_meta.get("slot", -1)
            if slot_index < 0:
                continue
            
            # Switch to this layer to read its data
            facade.switch_to_layer(slot_index, push_undo=False)
            
            # Get layer data
            layer_dict = facade.get_active_layer_dict()
            mask_dict = facade.get_active_mask_dict()
            
            # Prepare layer export
            layer_export = {
                "slot": slot_index,
                "name": layer_meta.get("name", f"Layer {slot_index}"),
                "visible": layer_meta.get("visible", True),
                "mask_default": layer_meta.get("mask_default", 0.0),
                "locks": layer_meta.get("locks", {}),
                "weights": {},
                "mask": {}
            }
            
            # Round weights
            for v_idx, bones_dict in layer_dict.items():
                rounded_bones = {
                    bone_name: round(weight, precision)
                    for bone_name, weight in bones_dict.items()
                }
                if rounded_bones:
                    layer_export["weights"][str(v_idx)] = rounded_bones
            
            # Round mask
            for v_idx, mask_value in mask_dict.items():
                if mask_value > 0.0:
                    layer_export["mask"][str(v_idx)] = round(mask_value, precision)
            
            export_data["layers"].append(layer_export)
        
        # Restore active layer
        facade.switch_to_layer(active_index, push_undo=False)
        
        # Write to file
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
            
            self.report({'INFO'}, f"Exported {len(export_data['layers'])} layers to: {os.path.basename(self.filepath)}")
            print(f"[Weight IO] Exported {len(export_data['layers'])} layers: {self.filepath}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}


class WM_OT_superskin_import_json(bpy.types.Operator, ImportHelper):
    bl_idname = "superskin.import_weight_json"
    bl_label = "Import Weights from JSON"
    bl_options = {'REGISTER', 'UNDO'}
    
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(
        default="*.json",
        options={'HIDDEN'}
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        """Import ALL layers (weights, masks, metadata) from JSON file."""
        from ...core.facade import CoreFacade
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No active mesh object")
            return {'CANCELLED'}
        
        # Read JSON file
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            import_data = raw_data
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read JSON: {str(e)}")
            return {'CANCELLED'}
        
        # Validate structure
        if "layers" not in import_data:
            self.report({'ERROR'}, "Invalid format: missing 'layers' key")
            return {'CANCELLED'}
        
        facade = CoreFacade(context)
        ctrl = facade.get_ctrl()
        
        # Check version compatibility
        version = import_data.get("version", 1)
        if version != 1:
            self.report({'WARNING'}, f"Version {version} may not be fully compatible")
        
        # Clear existing layers?
        # Option 1: Replace all layers
        # Option 2: Append/overwrite by slot
        # We'll use Option 1: Replace all (clear and rebuild)
        
        # Get current meta and clear layers
        current_meta = facade.get_meta_list()
        for meta in reversed(current_meta):
            slot = meta.get("slot", -1)
            if slot >= 0:
                ctrl.remove_layer(slot)
        
        # Rebuild layers from import data
        for layer_export in import_data["layers"]:
            slot = layer_export.get("slot", -1)
            if slot < 0:
                continue
            
            # Create layer with metadata
            name = layer_export.get("name", f"Layer {slot}")
            visible = layer_export.get("visible", True)
            mask_default = layer_export.get("mask_default", 0.0)
            locks = layer_export.get("locks", {})
            
            # Create layer
            new_slot = ctrl.create_layer(name=name, visible=visible, mask_default=mask_default)
            
            if new_slot >= 0:
                # Switch to new layer
                facade.switch_to_layer(new_slot, push_undo=False)
                
                # Import weights
                weights_dict = layer_export.get("weights", {})
                if weights_dict:
                    imported_weights = {int(k): v for k, v in weights_dict.items()}
                    facade.write_layer_dict(imported_weights)
                
                # Import mask
                mask_dict = layer_export.get("mask", {})
                if mask_dict:
                    imported_mask = {int(k): v for k, v in mask_dict.items()}
                    facade.write_mask_dict(imported_mask)
                
                # Set locks
                if locks:
                    # Update locks in metadata
                    # This requires core API support - will be handled by facade
                    pass
        
        # Restore active layer
        active_index = import_data.get("active_layer_index", 0)
        if active_index < len(import_data["layers"]):
            # Find the slot for this active layer
            for layer_export in import_data["layers"]:
                if layer_export.get("slot") == active_index:
                    facade.switch_to_layer(active_index, push_undo=False)
                    break
        
        facade.finish()
        
        self.report({'INFO'}, f"Imported {len(import_data['layers'])} layers from: {os.path.basename(self.filepath)}")
        print(f"[Weight IO] Imported {len(import_data['layers'])} layers: {self.filepath}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(WM_OT_superskin_export_json)
    bpy.utils.register_class(WM_OT_superskin_import_json)


def unregister():
    bpy.utils.unregister_class(WM_OT_superskin_import_json)
    bpy.utils.unregister_class(WM_OT_superskin_export_json)