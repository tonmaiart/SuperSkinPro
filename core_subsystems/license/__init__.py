"""SuperSkinPro License subsystem — closed module.

External code must only import ``LicenseService`` from this package.
``license_gateway`` is a private implementation detail.
"""

from importlib import reload

from .license_service import LicenseService
from . import license_gateway
from . import license_service


for mod in (license_gateway, license_service):
    try:
        reload(mod)
    except Exception:
        pass


def register():
    pass


def unregister():
    pass
