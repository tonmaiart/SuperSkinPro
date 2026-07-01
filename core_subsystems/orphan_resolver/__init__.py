"""Orphan bone resolver — selection operator and weight-op integration.

Orphan bones are bones whose name appears in ss_layer_N weight data but
no longer exists as a real vertex group (bone was renamed or deleted from
the armature). They appear in superskin_bones_collection with is_orphan=True.

User workflow:
  - Select orphan row → shader shows its weight (same as real bone)
  - Use Add/Scale/Smooth/Sharpen to paint weight away
  - When weight reaches 0 across all vertices → auto-pruned from storage

No manual remap or delete actions — weight ops handle cleanup automatically.
"""

from importlib import reload

from . import ops

for mod in (ops,):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    ops.register()


def unregister():
    ops.unregister()
