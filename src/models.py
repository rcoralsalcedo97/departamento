"""Canonical listing schema.

Every field is optional: UNKNOWN (None) is always preferred over a guessed value.
Fields ending in ``_basis`` record whether a monetary value was PUBLISHED by the
listing or CALCULATED by this pipeline from the documented FX rate.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Basis = Literal["PUBLISHED", "CALCULATED"]
ActiveStatus = Literal["ACTIVE_CONFIRMED", "LIKELY_ACTIVE", "UNKNOWN", "INACTIVE"]


class Listing(BaseModel):
    # provenance
    source: str
    source_listing_id: Optional[str] = None
    source_url: Optional[str] = None
    search_segment: Optional[str] = None        # bedroom search that returned it, e.g. "1BR"
    scraped_at: Optional[str] = None
    publication_date: Optional[str] = None
    last_updated_date: Optional[str] = None
    active_status: ActiveStatus = "UNKNOWN"
    active_evidence: Optional[str] = None

    # text
    title: Optional[str] = None
    description: Optional[str] = None

    # location
    district: Optional[str] = None
    subarea: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coord_source: Optional[str] = None          # LISTING / GEOCODED_ADDRESS / GEOCODED_TEXT / None
    coord_precision: Optional[str] = None       # EXACT / APPROXIMATE / STREET_NUMBER / STREET_LEVEL
    geocoding_confidence: Optional[str] = None  # HIGH / MEDIUM (geocoded points only)
    address_evidence: Optional[str] = None      # the listing text a geocode was based on

    # money (as published)
    rent_original: Optional[float] = None
    rent_currency: Optional[str] = None         # USD / PEN
    rent_pen: Optional[float] = None
    rent_usd: Optional[float] = None
    rent_pen_basis: Optional[Basis] = None
    rent_usd_basis: Optional[Basis] = None
    # Figures exactly as the portal published them (never overwritten). rent_usd above is the single
    # comparable value used for budget, ranking and USD/m²: the USD price when the listing is priced in
    # USD, otherwise the PEN price converted at the run's one documented FX rate.
    rent_usd_published: Optional[float] = None
    rent_pen_published: Optional[float] = None
    rent_usd_published_diff_pct: Optional[float] = None   # published USD vs USD calculated from PEN

    maintenance_fee: Optional[float] = None
    maintenance_currency: Optional[str] = None
    maintenance_pen: Optional[float] = None
    maintenance_usd: Optional[float] = None
    maintenance_pen_basis: Optional[Basis] = None
    maintenance_usd_basis: Optional[Basis] = None
    maintenance_included_in_rent: Optional[bool] = None

    estimated_total_monthly_pen: Optional[float] = None
    estimated_total_monthly_usd: Optional[float] = None
    fx_rate_usd_pen: Optional[float] = None

    # unit
    property_type: Optional[str] = None
    operation: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    total_area_m2: Optional[float] = None
    built_area_m2: Optional[float] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    parking_spaces: Optional[int] = None
    parking_included: Optional[bool] = None

    furnished: Optional[bool] = None
    semi_furnished: Optional[bool] = None
    balcony: Optional[bool] = None
    terrace: Optional[bool] = None
    laundry: Optional[bool] = None
    interior_view: Optional[bool] = None
    exterior_view: Optional[bool] = None
    acoustic_windows: Optional[bool] = None
    study: Optional[bool] = None
    walk_in_closet: Optional[bool] = None
    avenue_view: Optional[bool] = None          # text says unit faces an avenue
    quiet_claim: Optional[bool] = None          # seller claims "calle tranquila" etc. (weak evidence)
    studio_text: Optional[bool] = None          # "monoambiente", "tipo estudio", "loft"
    short_term_text: Optional[bool] = None      # "temporal", "por días", Airbnb-style
    shared_room_text: Optional[bool] = None     # room in a shared flat, not a whole unit
    internet_included: Optional[bool] = None

    # building
    elevator: Optional[bool] = None
    security_24h: Optional[bool] = None
    gym: Optional[bool] = None
    pool: Optional[bool] = None
    coworking: Optional[bool] = None
    common_areas: Optional[bool] = None
    pets_allowed: Optional[bool] = None

    # terms
    minimum_contract_months: Optional[int] = None
    deposit_months: Optional[float] = None
    advance_months: Optional[float] = None
    utilities_included: Optional[str] = None

    # contact
    agent_name: Optional[str] = None
    agency_name: Optional[str] = None
    advertiser_key: Optional[str] = None        # portal publisher id / logo path (dedupe evidence only)
    phone: Optional[str] = None
    whatsapp: Optional[str] = None

    # media
    main_image_url: Optional[str] = None
    image_count: Optional[int] = None
    image_keys: list[str] = Field(default_factory=list)   # CDN image ids, used for dedupe

    amenities: list[str] = Field(default_factory=list)
    raw_description: Optional[str] = None
    text_signals: list[str] = Field(default_factory=list)  # evidence phrases found in text

    def key(self) -> str:
        return f"{self.source}:{self.source_listing_id or self.source_url}"
