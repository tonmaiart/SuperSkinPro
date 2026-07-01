"""SuperSkinPro layer_manager subsystem — stateless layer metadata and compositing services.

Moved from core/layer_manager/. Operates on plain Python data structures
with no dependency on a live bpy.context.
"""

from importlib import reload

from . import compositor
from . import topology_healer
from . import layer_manager
from . import data_operations

for mod in (compositor, topology_healer, layer_manager, data_operations):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    pass


def unregister():
    pass
