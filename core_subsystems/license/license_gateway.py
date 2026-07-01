"""Gumroad license verification — Rust-accelerated portal.

No bpy import — pure dispatch to the native Rust core, same pattern as
``weight_calculator/smooth_logic.py``. The HTTPS call and the HMAC signing/
verification both happen inside the compiled binary; this module only ever
sees plain strings and booleans.
"""

from ..rust_weight_engine import RustWeightEngine as RustGateway

# This product's Gumroad API requires product_id (not product_permalink) —
# Gumroad's own verify response names the exact value to use for this product.
GUMROAD_PRODUCT_ID = "SNwmonGFn_waEKPkW369ZA=="


def verify_license(license_key: str) -> tuple:
    """Call Gumroad's License Verify API (requires internet).

    Returns ``(success, message, activation_token)``. *activation_token* is
    only non-empty when *success* is True.
    """
    rust = RustGateway("license_activation")
    return rust.call("rust_verify_gumroad_license", license_key, GUMROAD_PRODUCT_ID)


def check_cached_activation(license_key: str, activation_token: str) -> bool:
    """Offline re-check of a previously issued *activation_token*. No network."""
    if not license_key or not activation_token:
        return False
    rust = RustGateway("license_check")
    return rust.call("rust_check_cached_activation", license_key, activation_token)
