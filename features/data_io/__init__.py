from importlib import reload

from . import logic
from . import ops
from . import data_io_feature

for mod in (logic, ops, data_io_feature):
    try:
        reload(mod)
    except Exception:
        pass

def register():
    data_io_feature.register()
    ops.register()

def unregister():
    ops.unregister()
    data_io_feature.unregister()