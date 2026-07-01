"""LicenseGateway -- unified portal for Pro-activation state and feature gating.

Merges the responsibilities of the former license/license_gateway.py (Rust FFI
dispatch for Gumroad verification and HMAC token checking) and
license/license_service.py (persistence and feature-gating logic).

All methods are classmethods; no instance state is maintained.
Persistence routes through PreferencesService; the HTTPS call and HMAC
signing/verification happen inside the compiled Rust binary.

No bpy import -- operates on plain strings and booleans.
"""

from ..rust_weight_engine import RustWeightEngine
from ..preferences.preferences_service import PreferencesService

# This product's Gumroad API requires product_id (not product_permalink).
GUMROAD_PRODUCT_ID = "SNwmonGFn_waEKPkW369ZA=="

# Free-tier cap. Pro activation sets this to None (unlimited).
FREE_LAYER_LIMIT = 6


class LicenseGateway:
    """Stateless service -- all methods are classmethods, no instance state."""

    # =========================================================================
    #  Activation (network-dependent)
    # =========================================================================

    @classmethod
    def activate(cls, license_key: str) -> tuple[bool, str]:
        """Verify *license_key* against Gumroad (requires internet) and persist.

        Returns:
            ``(success, message)`` for the calling operator to report.
        """
        success, message, token = cls._verify_license(license_key)
        PreferencesService.set_license_activation(license_key, token, message)
        return success, message

    @classmethod
    def _verify_license(cls, license_key: str) -> tuple[bool, str, str]:
        """Call Gumroad's License Verify API.

        Returns ``(success, message, activation_token)``. *activation_token* is
        only non-empty when *success* is True.
        """
        rust = RustWeightEngine("license_activation")
        return rust.call("rust_verify_gumroad_license", license_key, GUMROAD_PRODUCT_ID)

    # =========================================================================
    #  Offline re-check
    # =========================================================================

    @classmethod
    def check_cached_activation(cls, license_key: str, activation_token: str) -> bool:
        """Offline re-check of a previously issued *activation_token*. No network."""
        if not license_key or not activation_token:
            return False
        rust = RustWeightEngine("license_check")
        return rust.call("rust_check_cached_activation", license_key, activation_token)

    # =========================================================================
    #  State queries
    # =========================================================================

    @classmethod
    def is_pro(cls) -> bool:
        """True if the cached activation token is currently valid.

        Always re-derives the signature via Rust rather than trusting a stored
        boolean -- see SSPrefLicense docstring for why.
        """
        key = PreferencesService.get_license_key()
        token = PreferencesService.get_activation_token()
        return cls.check_cached_activation(key, token)

    @classmethod
    def layer_limit(cls):
        """Return the max layer count for the current tier, or None if unlimited."""
        return None if cls.is_pro() else FREE_LAYER_LIMIT

    @classmethod
    def get_license_key(cls) -> str:
        return PreferencesService.get_license_key()

    @classmethod
    def get_activation_token(cls) -> str:
        return PreferencesService.get_activation_token()
