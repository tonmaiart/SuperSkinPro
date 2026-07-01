"""Operators package — centralised registry for all SuperSkinPro operators."""

from importlib import reload

from . import ops_preferences_lists
from . import ops_preferences


for mod in (ops_preferences_lists, ops_preferences):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    ops_preferences_lists.register()
    ops_preferences.register()


def unregister():
    ops_preferences.unregister()
    ops_preferences_lists.unregister()
