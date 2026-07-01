"""PrefsExtensionRegistry — allows feature domains to own their own
PropertyGroup classes, draw functions, and default values, while still
routing persistence through PreferencesService.

Feature domains call PrefsExtensionRegistry.register() from their
prefs.register() function. PreferencesService.load() / save_to_user_file()
iterate all registered specs automatically.
"""


class PrefsExtensionSpec:
    """Descriptor for one feature domain's preferences contribution.

    json_path:         tuple of keys to navigate in the full user.json dict,
                       e.g. ("customize", "bone_picker") or ("mirror",).
    section_title:     label shown in the Preferences section header.
    draw_tab:          'LAYER', 'SKINNING', 'CUSTOMIZE', or 'SYSTEM' — which
                       tab hosts this section.
    draw_section_fn:   fn(layout) → None. Draws the section body.
    populate_fn:       fn(data: dict) → None. Writes section data into the live
                       WindowManager PointerProperty.
    serialize_into_fn: fn(full_dict: dict) → None. Writes the live property
                       values back into the appropriate path of full_dict.
    defaults_path:     absolute path to the feature's default_config.json.
    collapsible:       When True (default), the section is wrapped in a
                       collapsible panel header. Primary viewer domains
                       (LayerViewer, DeformBoneViewer) set this to False so
                       their list widgets render at full width without a
                       collapsible wrapper.
    """

    __slots__ = (
        'json_key', 'json_path', 'section_title', 'draw_tab',
        'draw_section_fn', 'populate_fn', 'serialize_into_fn', 'defaults_path',
        'collapsible',
    )

    def __init__(self, json_key, json_path, section_title, draw_tab,
                 draw_section_fn, populate_fn, serialize_into_fn, defaults_path,
                 collapsible=True):
        self.json_key = json_key
        self.json_path = json_path
        self.section_title = section_title
        self.draw_tab = draw_tab
        self.draw_section_fn = draw_section_fn
        self.populate_fn = populate_fn
        self.serialize_into_fn = serialize_into_fn
        self.defaults_path = defaults_path
        self.collapsible = collapsible


class PrefsExtensionRegistry:
    """Class-level registry — no instance state, no bpy dependency."""

    _specs: list = []

    @classmethod
    def register(cls, spec: PrefsExtensionSpec) -> None:
        cls._specs = [s for s in cls._specs if s.json_key != spec.json_key]
        cls._specs.append(spec)

    @classmethod
    def unregister(cls, json_key: str) -> None:
        cls._specs = [s for s in cls._specs if s.json_key != json_key]

    @classmethod
    def get_all(cls) -> list:
        return list(cls._specs)

    @classmethod
    def get_by_tab(cls, tab: str) -> list:
        return [s for s in cls._specs if s.draw_tab == tab]
