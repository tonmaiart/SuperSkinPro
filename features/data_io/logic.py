import json
import os
import bpy

class WeightIOProcessor:
    @staticmethod
    def export_to_json(filepath: str, layer_dict: dict) -> bool:
        """Serializes active layer weight dictionaries into an external JSON file with float rounding."""
        try:
            wm = bpy.context.window_manager
            prefs = getattr(wm, "superskin_weight_io_prefs", None)
            precision = prefs.export_precision if prefs else 5

            exportable_data = {}
            for v_idx, bones_dict in layer_dict.items():
                rounded_bones = {
                    bone_name: round(weight, precision) 
                    for bone_name, weight in bones_dict.items()
                }
                exportable_data[str(v_idx)] = rounded_bones
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(exportable_data, f, indent=4)
            return True
        except Exception:
            return False

    @staticmethod
    def import_from_json(filepath: str) -> dict | None:
        """Parses foreign JSON weight data and casts keys back to native integer vertex primitives."""
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            return {int(k): v for k, v in raw_data.items()}
        except Exception:
            return None