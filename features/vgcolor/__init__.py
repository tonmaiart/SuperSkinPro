"""VGColor feature package — lifecycle and hot-reload bootstrap.

No ops.py/keymap.py -- this domain draws Blender's own native
`context.preferences.view` properties directly; it defines no operators
or keymaps of its own.
"""

from importlib import reload

from . import vgcolor_feature

for mod in (vgcolor_feature,):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    vgcolor_feature.register()


def unregister():
    vgcolor_feature.unregister()
