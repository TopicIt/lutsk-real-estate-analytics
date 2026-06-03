from __future__ import annotations

from config import OLX_RENT_APARTMENTS_URL, OLX_SALE_APARTMENTS_URL


def get_olx_count(url: str) -> int | None:
    """TODO: Read a public OLX search result count after the strategy is approved."""
    # TODO: Add a compliant, rate-limited implementation only after legal/API review.
    # TODO: Keep this function side-effect free except for the approved OLX request.
    # TODO: Return None when the count cannot be trusted.
    raise NotImplementedError("OLX automatic collection is planned but not active.")


def collect_olx_counts() -> dict:
    """TODO: Collect the configured OLX apartment counts without writing database rows."""
    # TODO: Use OLX_SALE_APARTMENTS_URL and OLX_RENT_APARTMENTS_URL once configured.
    # TODO: Preserve existing analytics semantics: source='OLX', data_source='manual' or
    # a separately reviewed data_source value only after the dashboard contract is updated.
    # TODO: Add explicit operator opt-in before any network call is enabled.
    configured_urls = {
        "sale_apartments_all": OLX_SALE_APARTMENTS_URL,
        "rent_apartments_all": OLX_RENT_APARTMENTS_URL,
    }
    return {key: None for key, url in configured_urls.items() if url}
