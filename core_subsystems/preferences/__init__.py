"""SuperSkinPro Preferences — core_subsystems backend layer.

Provides PreferencesService and Blender PropertyGroup definitions.
Blender lifecycle registration (load_post handler, temp-VG recovery) is
owned by core/preferences/__init__.py to avoid an upward dependency on
core/layer_storage from inside core_subsystems.

External code must only import ``PreferencesService`` from this package.
``io`` and ``property_groups`` are private implementation details.
"""

from importlib import reload

from .preferences_service import PreferencesService
from . import io
from . import property_groups
from . import preferences_service


for mod in (io, property_groups, preferences_service):
    try:
        reload(mod)
    except Exception:
        pass
