"""Weight-apply domain package — Add, Scale, Smooth, Sharpen operators + logic."""

from importlib import reload

from . import ui
from . import logic
from . import ops
from . import weight_apply_feature

for mod in (ui, logic, ops, weight_apply_feature):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    weight_apply_feature.register()
    ops.register()


def unregister():
    ops.unregister()
    weight_apply_feature.unregister()
