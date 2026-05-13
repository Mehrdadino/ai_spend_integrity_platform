"""Map optional ``service_hint`` + label text → ``canonical_service_key`` (2c).

Keys are namespaced ``domain_family`` strings (no DB enum) so new domains only
extend this module.
"""

from __future__ import annotations

# Utility — electric / gas / water (extend for steam, chilled water, …)
SERVICE_UTILITY_ELECTRIC = "utility_electric"
SERVICE_UTILITY_NATURAL_GAS = "utility_natural_gas"
SERVICE_UTILITY_WATER = "utility_water"
SERVICE_UTILITY_SEWER = "utility_sewer"

# Telecom (extend for voice lines, TV bundles, …)
SERVICE_TELECOM_BROADBAND = "telecom_broadband"

# Contracts / SaaS (placeholder for future contract-drift features)
SERVICE_CONTRACT_VENDOR = "contract_vendor"

SERVICE_UNKNOWN = "unknown"


def infer_service_key(*, raw_label: str, service_hint: str | None) -> str:
    """Return a stable service key; never raises."""
    hint = (service_hint or "").strip().lower()
    if hint in ("electric", "electricity", "power", "kwh"):
        return SERVICE_UTILITY_ELECTRIC
    if hint in ("gas", "natural_gas", "natural gas", "therm", "ccf"):
        return SERVICE_UTILITY_NATURAL_GAS
    if hint in ("water", "potable"):
        return SERVICE_UTILITY_WATER
    if hint in ("sewer", "wastewater", "waste water"):
        return SERVICE_UTILITY_SEWER
    if hint in ("internet", "broadband", "fiber", "isp", "data"):
        return SERVICE_TELECOM_BROADBAND
    if hint in ("contract", "saas", "subscription", "license"):
        return SERVICE_CONTRACT_VENDOR

    t = raw_label.strip().lower()
    if any(x in t for x in ("electric", "kwh", "kilowatt", "delivery", "transmission")):
        return SERVICE_UTILITY_ELECTRIC
    if any(x in t for x in ("gas", "therm", "ccf", "natural gas")):
        return SERVICE_UTILITY_NATURAL_GAS
    if "water" in t and "sewer" not in t:
        return SERVICE_UTILITY_WATER
    if "sewer" in t or "wastewater" in t:
        return SERVICE_UTILITY_SEWER
    if any(x in t for x in ("internet", "broadband", "mbps", "fiber", "isp")):
        return SERVICE_TELECOM_BROADBAND

    return SERVICE_UNKNOWN
