"""Interface utilities sub-package — context switches, handlers, caches,
GPU primitives, and shared operator dispatch.

Module-level imports are restricted to gpu_utils (no core/ deps).
utils.py and op_exec.py are imported lazily by interface._ensure_deferred()
to avoid circular imports when core/shaders/shader_utils triggers loading
during core/ initialisation.
"""

from importlib import reload

# gpu_utils is safe — only imports ctypes and gpu (Blender built-ins)
from . import gpu_utils

try:
    reload(gpu_utils)
except Exception:
    pass

# utils and op_exec depend on core/ or core_subsystems/ — imported lazily
# via interface._ensure_deferred().  The lazy modules are:
#   - utils:   needs core.facade, core_subsystems.*
#   - op_exec: needs interface.registry (already loaded), core.facade


def register():
    """Called by interface.register(). Leaf modules are already loaded."""
    pass


def unregister():
    """Called by interface.unregister(). Leaf modules are already loaded."""
    pass
