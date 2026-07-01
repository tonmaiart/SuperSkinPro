"""PreferencesService — sole authority bridging JSON files and the live PropertyGroup.

External code accesses core preferences exclusively through the resolved accessor
methods on this class. Feature-domain preferences are accessed via their own
WindowManager properties, but they register with PrefsExtensionRegistry so
load/save/reset still routes through this service.
"""

import bpy

from . import io


# Cache the default dict (loaded once, never changes at runtime).
_default_dict = None


def _get_default_dict() -> dict:
    global _default_dict
    if _default_dict is None:
        path = io.default_json_path()
        _default_dict = io.load_json_safe(path)
        if not _default_dict:
            print(f"⚠️ [SuperSkinPro] default_prefs.json not found or empty at {path} "
                  f"— preferences will start blank.")
    return _default_dict


def _get_nested(d: dict, path: tuple) -> dict:
    """Navigate a nested dict by a tuple of keys, returning {} on any miss."""
    node = d
    for key in path:
        if not isinstance(node, dict):
            return {}
        node = node.get(key, {})
    return node if isinstance(node, dict) else {}


def _default_single_stops() -> list:
    default = _get_default_dict()
    stops_raw = default.get("customize", {}).get("single_ramp", {}).get("stops", [])
    return [(float(s[0]), tuple(float(c) for c in s[1])) for s in stops_raw]


def _default_mask_stops() -> list:
    default = _get_default_dict()
    stops_raw = default.get("customize", {}).get("mask_ramp", {}).get("stops", [])
    return [(float(s[0]), tuple(float(c) for c in s[1])) for s in stops_raw]


class PreferencesService:
    """Stateless service for reading/writing preferences via JSON files."""

    @classmethod
    def load(cls) -> None:
        """Read default.json + user.json, merge, populate core + extension PropertyGroups."""
        from SuperSkinPro.registry.prefs_extension_registry import PrefsExtensionRegistry
        from SuperSkinPro.registry.unified_feature_api import UnifiedRegistry

        default = _get_default_dict()
        user    = io.load_json_safe(io.user_json_path())
        merged  = io.deep_merge(default, user)

        prefs = bpy.context.window_manager.superskin_prefs
        cls._populate_from_dict(prefs, merged)

        # Load each feature extension using its own default_config.json + user section.
        # Legacy PrefsExtensionRegistry path
        for spec in PrefsExtensionRegistry.get_all():
            ext_defaults = io.load_json_safe(spec.defaults_path)
            user_section = _get_nested(user, spec.json_path)
            ext_data     = io.deep_merge(ext_defaults, user_section)
            try:
                spec.populate_fn(ext_data)
            except Exception as e:
                print(f"⚠️ [SuperSkinPro] Failed to load prefs for '{spec.json_key}': {e}")

        # UnifiedRegistry path
        for ext in UnifiedRegistry.get_all():
            defaults_path = ext.get_defaults_path()
            if defaults_path is None:
                continue
            ext_defaults = io.load_json_safe(defaults_path)
            user_section = _get_nested(user, ext.get_json_path())
            ext_data     = io.deep_merge(ext_defaults, user_section)
            try:
                ext.populate(ext_data)
            except Exception as e:
                print(f"⚠️ [SuperSkinPro] Failed to load unified prefs for '{ext.get_id()}': {e}")

        print(f"🔍 [SuperSkinPro Prefs] load() complete: "
              f"single_ramp={len(prefs.customize.single_ramp.stops)} stops, "
              f"mask_ramp={len(prefs.customize.mask_ramp.stops)} stops, "
              f"multi_palette={len(prefs.customize.multi_palette.colors)} colors")

    @classmethod
    def save_to_user_file(cls) -> None:
        """Serialize core + all extension prefs and write to user.json."""
        from SuperSkinPro.registry.prefs_extension_registry import PrefsExtensionRegistry
        from SuperSkinPro.registry.unified_feature_api import UnifiedRegistry

        prefs = bpy.context.window_manager.superskin_prefs
        data  = cls._dict_from_property_group(prefs)

        # Legacy PrefsExtensionRegistry path
        for spec in PrefsExtensionRegistry.get_all():
            try:
                spec.serialize_into_fn(data)
            except Exception as e:
                print(f"⚠️ [SuperSkinPro] Failed to serialize prefs for '{spec.json_key}': {e}")

        # UnifiedRegistry path
        for ext in UnifiedRegistry.get_all():
            try:
                ext.serialize_into(data)
            except Exception as e:
                print(f"⚠️ [SuperSkinPro] Failed to serialize unified prefs for '{ext.get_id()}': {e}")

        io.save_json(io.user_json_path(), data)

    @classmethod
    def reset_to_default(cls) -> None:
        """Load default values directly (no merge) into all PropertyGroups."""
        from SuperSkinPro.registry.prefs_extension_registry import PrefsExtensionRegistry
        from SuperSkinPro.registry.unified_feature_api import UnifiedRegistry

        default = _get_default_dict()
        prefs   = bpy.context.window_manager.superskin_prefs
        cls._populate_from_dict(prefs, default)

        # Legacy PrefsExtensionRegistry path
        for spec in PrefsExtensionRegistry.get_all():
            ext_defaults = io.load_json_safe(spec.defaults_path)
            try:
                spec.populate_fn(ext_defaults)
            except Exception as e:
                print(f"⚠️ [SuperSkinPro] Failed to reset prefs for '{spec.json_key}': {e}")

        # UnifiedRegistry path
        for ext in UnifiedRegistry.get_all():
            defaults_path = ext.get_defaults_path()
            if defaults_path is None:
                continue
            ext_defaults = io.load_json_safe(defaults_path)
            try:
                ext.populate(ext_defaults)
            except Exception as e:
                print(f"⚠️ [SuperSkinPro] Failed to reset unified prefs for '{ext.get_id()}': {e}")

    # ── Resolved accessors for core prefs (hot-path) ──

    @classmethod
    def get_single_ramp_stops(cls) -> list:
        prefs = bpy.context.window_manager.superskin_prefs
        stops = prefs.customize.single_ramp.stops
        return [(s.position, (s.color[0], s.color[1], s.color[2])) for s in stops]

    @classmethod
    def get_mask_ramp_stops(cls) -> list:
        prefs = bpy.context.window_manager.superskin_prefs
        stops = prefs.customize.mask_ramp.stops
        return [(s.position, (s.color[0], s.color[1], s.color[2])) for s in stops]

    @classmethod
    def get_multi_palette(cls) -> list:
        prefs  = bpy.context.window_manager.superskin_prefs
        colors = prefs.customize.multi_palette.colors
        return [(c.color[0], c.color[1], c.color[2]) for c in colors]

    # ── Mirror accessors — delegate to MirrorPreferencesService ──

    @classmethod
    def get_mirror_axis(cls) -> str:
        from SuperSkinPro.features.mirror.mirror_feature import MirrorPreferencesService
        return MirrorPreferencesService.get_mirror_axis()

    @classmethod
    def get_mirror_direction(cls) -> str:
        from SuperSkinPro.features.mirror.mirror_feature import MirrorPreferencesService
        return MirrorPreferencesService.get_mirror_direction()

    @classmethod
    def get_mirror_both_data(cls) -> bool:
        from SuperSkinPro.features.mirror.mirror_feature import MirrorPreferencesService
        return MirrorPreferencesService.get_mirror_both_data()

    @classmethod
    def get_mirror_search_replace_pairs(cls) -> list:
        from SuperSkinPro.features.mirror.mirror_feature import MirrorPreferencesService
        return MirrorPreferencesService.get_mirror_search_replace_pairs()

    # ── Ramp customization checks ──

    @classmethod
    def is_single_ramp_customized(cls) -> bool:
        current = cls.get_single_ramp_stops()
        default = _default_single_stops()
        if len(current) != len(default):
            return True
        for (cp, cc), (dp, dc) in zip(current, default):
            if abs(cp - dp) > 1e-7:
                return True
            for i in range(3):
                if abs(cc[i] - dc[i]) > 1e-7:
                    return True
        return False

    @classmethod
    def is_mask_ramp_customized(cls) -> bool:
        current = cls.get_mask_ramp_stops()
        default = _default_mask_stops()
        if len(current) != len(default):
            return True
        for (cp, cc), (dp, dc) in zip(current, default):
            if abs(cp - dp) > 1e-7:
                return True
            for i in range(3):
                if abs(cc[i] - dc[i]) > 1e-7:
                    return True
        return False

    # ── License accessors ──

    @classmethod
    def get_license_key(cls) -> str:
        return bpy.context.window_manager.superskin_prefs.license.license_key

    @classmethod
    def get_activation_token(cls) -> str:
        return bpy.context.window_manager.superskin_prefs.license.activation_token

    @classmethod
    def get_license_status_message(cls) -> str:
        return bpy.context.window_manager.superskin_prefs.license.status_message

    @classmethod
    def set_license_activation(cls, license_key: str, activation_token: str, status_message: str) -> None:
        prefs = bpy.context.window_manager.superskin_prefs
        prefs.license.activation_token = activation_token
        prefs.license.status_message   = status_message
        prefs.license.license_key      = license_key
        cls.save_to_user_file()

    # ═══════════════════════════════════════════════════════════════════════
    #  Internal helpers — core PropertyGroup ↔ dict conversion
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _populate_from_dict(prefs, data: dict) -> None:
        """Write merged dict values into the core PropertyGroup, clearing collections first."""
        cdata = data.get("customize", {})

        # ── Single Ramp ──
        stops_coll = prefs.customize.single_ramp.stops
        stops_coll.clear()
        for stop in cdata.get("single_ramp", {}).get("stops", []):
            s = stops_coll.add()
            s.position = float(stop[0])
            s.color    = tuple(stop[1])

        # ── Mask Ramp ──
        stops_coll = prefs.customize.mask_ramp.stops
        stops_coll.clear()
        for stop in cdata.get("mask_ramp", {}).get("stops", []):
            s = stops_coll.add()
            s.position = float(stop[0])
            s.color    = tuple(stop[1])

        # ── Multi Palette (fixed 10 items) ──
        colors_coll = prefs.customize.multi_palette.colors
        colors_coll.clear()
        for color in cdata.get("multi_palette", {}).get("colors", []):
            c = colors_coll.add()
            c.color = tuple(color)

        # ── License ──
        lic = data.get("license", {})
        prefs.license.activation_token = lic.get("activation_token", "")
        prefs.license.status_message   = lic.get("status_message",   "")
        prefs.license.license_key      = lic.get("license_key",      "")

    @staticmethod
    def _dict_from_property_group(prefs) -> dict:
        """Serialize the core PropertyGroup back into a dict for user.json.

        Extensions add their own sections afterward via serialize_into_fn.
        """
        customize = {
            "single_ramp": {
                "stops": [[s.position, list(s.color)]
                           for s in prefs.customize.single_ramp.stops]
            },
            "mask_ramp": {
                "stops": [[s.position, list(s.color)]
                           for s in prefs.customize.mask_ramp.stops]
            },
            "multi_palette": {
                "colors": [list(c.color) for c in prefs.customize.multi_palette.colors]
            },
        }

        lic = prefs.license
        return {
            "_schema_version": 1,
            "customize": customize,
            "license": {
                "license_key":      lic.license_key,
                "activation_token": lic.activation_token,
                "status_message":   lic.status_message,
            },
        }
