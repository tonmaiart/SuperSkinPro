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

# PreferencesService is deliberately NOT hoisted here. core_subsystems/__init__.py
# reloads license_gateway before preferences (see that file's module list), so
# a module-level import here would bind to the pre-reload PreferencesService
# class -- a different object than the one load()/save_to_user_file() actually
# operate on, which silently defeats the `_loading` reentrancy guard. Every
# call site below imports it fresh instead. See docs/bug-history for the
# write-up this class of bug was diagnosed from.

# This product's Gumroad API requires product_id (not product_permalink).
GUMROAD_PRODUCT_ID = "SNwmonGFn_waEKPkW369ZA=="


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
        from ..preferences.preferences_service import PreferencesService
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
        from ..preferences.preferences_service import PreferencesService
        key = PreferencesService.get_license_key()
        token = PreferencesService.get_activation_token()
        return cls.check_cached_activation(key, token)

    @classmethod
    def get_license_key(cls) -> str:
        from ..preferences.preferences_service import PreferencesService
        return PreferencesService.get_license_key()

    @classmethod
    def get_activation_token(cls) -> str:
        from ..preferences.preferences_service import PreferencesService
        return PreferencesService.get_activation_token()
