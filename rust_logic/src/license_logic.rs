use hmac::{Hmac, Mac};
use serde::Deserialize;
use sha2::Sha256;

type HmacSha256 = Hmac<Sha256>;

// Compiled into the binary, never present in any Python source file — the point
// is that the boolean "is this Pro" decision can't be flipped by hand-editing a
// .py file or user_prefs.json, since reproducing a valid token requires this key.
const LICENSE_SIGNING_SECRET: &[u8] = b"SuperSkinPro-license-v1-9f3a7c2e4b6d1a08";

#[derive(Deserialize, Default)]
struct GumroadPurchase {
    #[serde(default)]
    refunded: bool,
    #[serde(default)]
    disputed: bool,
    #[serde(default)]
    chargebacked: bool,
}

#[derive(Deserialize)]
struct GumroadResponse {
    success: bool,
    #[serde(default)]
    message: Option<String>,
    #[serde(default)]
    purchase: Option<GumroadPurchase>,
}

fn sign_token(license_key: &str) -> String {
    let mut mac = HmacSha256::new_from_slice(LICENSE_SIGNING_SECRET)
        .expect("HMAC accepts a key of any length");
    mac.update(license_key.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

/// Verify *license_key* against Gumroad's License Verify API (requires internet).
///
/// Returns `(success, message, activation_token)`. On success, *activation_token*
/// is an HMAC-SHA256 signature over the license key that the caller persists and
/// later re-checks offline via [`check_cached_activation`] — network access is
/// only required for this one call, not for every subsequent session.
pub fn verify_gumroad_license(license_key: String, product_id: String) -> (bool, String, String) {
    let trimmed = license_key.trim();
    if trimmed.is_empty() {
        return (false, "License key is empty".to_string(), String::new());
    }

    let result = ureq::post("https://api.gumroad.com/v2/licenses/verify").send_form(&[
        ("product_id", product_id.as_str()),
        ("license_key", trimmed),
        ("increment_uses_count", "false"),
    ]);

    let response = match result {
        Ok(resp) => resp,
        Err(ureq::Error::Status(_code, resp)) => resp,
        Err(e) => {
            return (
                false,
                format!("Could not reach Gumroad — check your internet connection ({e})"),
                String::new(),
            );
        }
    };

    let body: GumroadResponse = match response.into_json() {
        Ok(b) => b,
        Err(e) => {
            return (
                false,
                format!("Unexpected response from Gumroad: {e}"),
                String::new(),
            );
        }
    };

    if !body.success {
        let msg = body.message.unwrap_or_else(|| "Invalid license key".to_string());
        return (false, msg, String::new());
    }

    if let Some(purchase) = &body.purchase {
        if purchase.refunded {
            return (false, "This license has been refunded".to_string(), String::new());
        }
        if purchase.disputed || purchase.chargebacked {
            return (false, "This license is under dispute".to_string(), String::new());
        }
    }

    (true, "Activated".to_string(), sign_token(trimmed))
}

/// Offline re-check: does *token* match what we'd compute for *license_key* now?
///
/// No network call — this is what runs on every session start. Recomputing the
/// signature (rather than trusting a stored boolean) means a hand-edited
/// `user_prefs.json` with `activation_token` left blank or guessed can't pass.
pub fn check_cached_activation(license_key: String, token: String) -> bool {
    let trimmed = license_key.trim();
    if trimmed.is_empty() || token.is_empty() {
        return false;
    }
    sign_token(trimmed) == token
}
