from importlib import reload

from . import ops
from . import weight_transfer_feature
from . import ui

for mod in (ops, weight_transfer_feature, ui):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    ops.register()
    weight_transfer_feature.register()


def unregister():
    weight_transfer_feature.unregister()
    ops.unregister()
