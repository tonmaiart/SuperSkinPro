"""LicenseService — sole authority for Pro-activation state and feature gating.

External code must only import ``LicenseService`` from this package, mirroring
the ``PreferencesService`` pattern in ``core/preferences/``.

Persistence note: this subsystem reads and writes license data through
``PreferencesService`` (core/preferences/). That upward dependency is a
deliberate, documented exception — ``PreferencesService`` is a generic I/O
utility, not a domain concern, and the license subsystem was originally part of
core itself. See ``core_subsystems/README.md`` for the full import invariants.
"""

from . import license_gateway
from ..preferences.preferences_service import PreferencesService

# Free-tier cap for the first gated feature (layer count). Pro activation lifts
# this entirely (None == unlimited). Future gated features should add their
# own constant here, following this same pattern, rather than hardcoding
# limits at the call site.
FREE_LAYER_LIMIT = 6


class LicenseService:
    """Stateless service — all methods are classmethods, no instance state."""

    @classmethod
    def activate(cls, license_key: str) -> tuple:
        """Verify *license_key* against Gumroad (requires internet) and persist the result.

        Returns ``(success, message)`` for the calling operator to report.
        """
        success, message, token = license_gateway.verify_license(license_key)
        PreferencesService.set_license_activation(license_key, token, message)
        return success, message

    @classmethod
    def get_license_key(cls) -> str:
        """Return the stored license key string."""
        return PreferencesService.get_license_key()

    @classmethod
    def get_activation_token(cls) -> str:
        """Return the cached HMAC activation token string."""
        return PreferencesService.get_activation_token()

    @classmethod
    def is_pro(cls) -> bool:
        """True if the cached activation token is currently valid.

        Always re-derives the signature via Rust rather than trusting a
        stored boolean — see ``SSPrefLicense`` docstring for why.
        """
        key = PreferencesService.get_license_key()
        token = PreferencesService.get_activation_token()
        return license_gateway.check_cached_activation(key, token)

    @classmethod
    def layer_limit(cls):
        """Return the max layer count for the current tier, or None if unlimited."""
        return None if cls.is_pro() else FREE_LAYER_LIMIT
