"""Fixes from the first live validation: cost accounting, Actor field mapping, bedroom segments,
currency normalisation, evidence-based geocoding and cross-portal de-duplication.

Record shapes below are copied from real Urbania/Adondevivir Actor output (free-plan list level)."""
import pandas as pd
import pytest

from src.deduplicate.dedupe import deduplicate
from src.geospatial.geocode import _judge, address_evidence
from src.models import Listing
from src.normalize.currency import apply_currency
from src.normalize.normalize import normalize_listing
from src.scoring.scoring import red_flags
from src.sources import navent
from src.sources.apify_client import (ApifyError, BudgetStop, charged_from_record, event_prices, paid_run,
                                      worst_case_cost)
from src.sources.base import CostBudget, SourceResult
from src.sources.navent import map_navent_record

URBANIA = {
    "imageUrl": "https://img10.naventcdn.com/avisos/111/01/50/85/00/58/360x266/1626734434.jpg?isFirstImage=true",
    "title": "Departamento · 40m² · 1 Dormitorio · Alquiler Departamento en Miraflores",
    "price": 2800, "currency": "PEN", "priceUsd": 740, "pricePen": 2800,
    "maintenanceFee": 260, "maintenanceFeeCurrency": "PEN", "operationType": "alquiler", "propertyType": "Departamento",
    "bedrooms": 1, "bathrooms": 1, "totalAreaM2": 40, "location": "Alexander Von Humboldt, Miraflores",
    "description": "Se alquila departamento de 1 dormitorio con balcón, cocina equipada y área de lavandería. " * 3,
    "publisherLogo": "https://img10.naventcdn.com/empresas/111/00/01/70/12/34/130x70/logo_demo-agente_1786571938142.jpg",
    "url": "https://urbania.pe/inmueble/clasificado/alclapin-alquiler-de-departamento-en-miraflores-150850058",
    "listingId": "150850058", "observedAt": "2026-09-25T00:31:40.267Z", "detailError": None, "error": None,
    "pricePerM2": 70, "pricePerM2Currency": "PEN",
}
ADONDEVIVIR = {**URBANIA, "listingId": "150850070", "isDevelopment": False,
               "imageUrl": "https://img10.naventcdn.com/avisos/111/01/50/85/00/58/360x266/1626734434.jpg"
                           "?rapc=bXZhX2ltYWdl?isFirstImage=true",
               "url": "https://www.adondevivir.com/propiedades/clasificado/alclapin-alquiler-departamento-150850070.html"}


# --------------------------------------------------------------------------- mapping
def test_total_area_m2_from_actor_record():
    lst = map_navent_record(URBANIA, "urbania", "https://urbania.pe", "2026-09-24T19:31:00-05:00")
    assert lst.total_area_m2 == 40


def test_actor_list_record_fields():
    lst = map_navent_record({**URBANIA, "_search_segment": "1BR"}, "urbania", "https://urbania.pe")
    assert (lst.district, lst.subarea) == ("Miraflores", "Alexander Von Humboldt")
    assert lst.main_image_url.startswith("https://img10.naventcdn.com/") and lst.image_keys == ["1626734434"]
    assert lst.advertiser_key == "logo:111000170123 4".replace(" ", "")
    assert (lst.rent_pen_published, lst.rent_usd_published) == (2800, 740)
    assert lst.search_segment == "1BR"
    assert lst.phone is None and lst.publication_date is None      # not in free-plan output: stays UNKNOWN


def test_location_district_city_form():
    lst = map_navent_record({**URBANIA, "location": "Miraflores, Lima"}, "urbania", "https://urbania.pe")
    assert lst.district == "Miraflores" and lst.subarea == "Lima"
    other = map_navent_record({**URBANIA, "location": "San Juan de Miraflores, Lima"}, "urbania", "https://urbania.pe")
    assert other.district == "San Juan de Miraflores"


def test_documented_detail_fields_are_mapped():
    rec = {**URBANIA, "builtAreaM2": 38, "agentPhone": "+51961891527", "agentWhatsapp": "+51961891527",
           "publishedDate": "2026-09-04T07:12:13Z", "coordinates": {"lat": -12.121, "lng": -77.03}}
    lst = map_navent_record(rec, "adondevivir", "https://www.adondevivir.com")
    assert lst.built_area_m2 == 38 and lst.phone and lst.whatsapp and lst.publication_date == "2026-09-04"
    assert lst.latitude == -12.121 and lst.coord_source == "LISTING"


# --------------------------------------------------------------------------- currency
def test_pen_priced_listing_is_normalised_and_published_usd_kept(cfg, fx):
    lst = apply_currency(map_navent_record(URBANIA, "urbania", "https://urbania.pe"), fx)
    assert lst.rent_usd == round(2800 / 3.40, 2) and lst.rent_usd_basis == "CALCULATED"
    assert lst.rent_usd_published == 740 and lst.rent_pen_published == 2800 and lst.rent_pen == 2800
    assert lst.rent_usd_published_diff_pct == pytest.approx(-10.1, abs=0.05)
    assert "CURRENCY_CONVERSION_MISMATCH" in red_flags(lst.model_dump(), cfg, [])


def test_small_published_gap_is_not_flagged(cfg, fx):
    lst = apply_currency(map_navent_record({**URBANIA, "priceUsd": 820}, "urbania", "https://urbania.pe"), fx)
    assert abs(lst.rent_usd_published_diff_pct) < 5
    assert "CURRENCY_CONVERSION_MISMATCH" not in red_flags(lst.model_dump(), cfg, [])


def test_usd_priced_listing_keeps_its_usd_price(fx):
    lst = apply_currency(Listing(source="t", rent_original=900, rent_currency="USD", rent_pen=3000,
                                 rent_pen_basis="PUBLISHED"), fx)
    assert lst.rent_usd == 900 and lst.rent_usd_basis == "PUBLISHED" and lst.rent_pen == 3000
    assert lst.rent_usd_published_diff_pct == pytest.approx(100 * (900 - 3000 / 3.4) / (3000 / 3.4), abs=0.05)


# --------------------------------------------------------------------------- de-duplication
def _frame(cfg, fx, *recs):
    rows = [normalize_listing(map_navent_record(r, src, base), cfg, fx).model_dump() for r, src, base in recs]
    return deduplicate(pd.DataFrame(rows), cfg)


def test_real_cross_post_is_grouped(cfg, fx):
    df = _frame(cfg, fx, (URBANIA, "urbania", "https://urbania.pe"),
                (ADONDEVIVIR, "adondevivir", "https://www.adondevivir.com"))
    assert df["duplicate_group_id"].nunique() == 1
    ev = df["dedupe_evidence"].iloc[0]
    assert "shared photo id" in ev and "same advertiser" in ev


def test_matching_price_area_maintenance_alone_do_not_merge(cfg, fx):
    other = {**ADONDEVIVIR, "listingId": "151000001",
             "imageUrl": "https://img10.naventcdn.com/avisos/111/01/51/00/00/01/360x266/1700000001.jpg",
             "publisherLogo": "https://img10.naventcdn.com/empresas/111/00/09/99/99/99/130x70/logo_otro.jpg",
             "description": "Flat moderno cerca al parque, edificio nuevo con gimnasio y terraza compartida. " * 3,
             "url": "https://www.adondevivir.com/propiedades/clasificado/otro-151000001.html"}
    df = _frame(cfg, fx, (URBANIA, "urbania", "https://urbania.pe"), (other, "adondevivir", "https://www.adondevivir.com"))
    assert df["duplicate_group_id"].nunique() == 2


def test_different_bathrooms_block_merge_despite_shared_photo(cfg, fx):
    df = _frame(cfg, fx, (URBANIA, "urbania", "https://urbania.pe"),
                ({**ADONDEVIVIR, "bathrooms": 2, "totalAreaM2": 55, "price": 3400, "pricePen": 3400},
                 "adondevivir", "https://www.adondevivir.com"))
    assert df["duplicate_group_id"].nunique() == 2


# --------------------------------------------------------------------------- geocoding evidence
@pytest.mark.parametrize("text,kind", [
    ("Depa en Calle Schell 345, Miraflores", "STREET_NUMBER"),
    ("Av. José Pardo N° 620 piso 8", "STREET_NUMBER"),
    ("Ubicado en Miraflores, Cdra. 61 de Av. Paseo de la República)", "STREET_BLOCK"),
    ("Av. Pardo cuadra 5", "STREET_BLOCK"),
    ("a 2 cuadras de Av. Larco 1150", None),
    ("cerca al Parque Kennedy", None),
    ("Av. Larco con 120 m2", None),
    ("Miraflores, Lima", None),
    ("San Antonio, Miraflores", None),
])
def test_address_evidence(text, kind):
    ev = address_evidence(None, None, text)
    assert (ev["kind"] if ev else None) == kind


def test_geocode_confidence_levels():
    ev = {"kind": "STREET_NUMBER", "street": "Calle Schell", "number": "345"}
    house = {"address": {"road": "Calle Schell", "house_number": "345"}}
    road = {"address": {"road": "Calle Schell"}}
    assert _judge(house, ev) == ("HIGH", "STREET_NUMBER")
    assert _judge(road, ev) == ("MEDIUM", "STREET_LEVEL")
    assert _judge({"address": {"road": "Avenida Larco"}}, ev) is None


# --------------------------------------------------------------------------- cost accounting
RUN_RECORD = {   # shape of a real Urbania run record (validation 2026-09-25)
    "id": "run1", "status": "SUCCEEDED", "usageTotalUsd": 0.01,          # stale: read right after the run ended
    "chargedEventCounts": {"result": 10, "details": 0, "apify-actor-start": 1},
    "pricingInfo": {"pricingModel": "PAY_PER_EVENT", "pricingPerEvent": {"actorChargeEvents": {
        "result": {"eventPriceUsd": 0.012, "isOneTimeEvent": False},
        "details": {"eventPriceUsd": 0.009231, "isOneTimeEvent": False},
        "apify-actor-start": {"eventPriceUsd": 0.01, "isOneTimeEvent": True}}}},
}
ACTOR_INFO = {"pricingInfos": [{"pricingModel": "PAY_PER_EVENT", "pricingPerEvent": {"actorChargeEvents": {
    "result": {"isOneTimeEvent": False, "eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.012},
                                                                  "BRONZE": {"tieredEventPriceUsd": 0.011782}}},
    "details": {"isOneTimeEvent": False, "eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.009231}}},
    "ai_translate": {"isOneTimeEvent": False, "eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.012}}},
    "apify-actor-start": {"isOneTimeEvent": True, "eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.01}}},
}}}]}


def test_actual_charge_from_run_record():
    cost, detail = charged_from_record(RUN_RECORD)
    assert cost == pytest.approx(0.13) and "result 10×0.0120" in detail


def test_tiered_prices_resolve_to_the_highest_tier():
    assert event_prices(ACTOR_INFO["pricingInfos"][0])["result"] == 0.012


def test_worst_case_includes_start_and_details_but_not_disabled_ai():
    worst, _ = worst_case_cost(ACTOR_INFO, 5, {"withDetails": True})
    assert worst == pytest.approx(0.01 + 5 * (0.012 + 0.009231))
    worst_ai, _ = worst_case_cost(ACTOR_INFO, 5, {"withAiTranslate": True})
    assert worst_ai == pytest.approx(worst + 5 * 0.012)


class FakeClient:
    def __init__(self, fail=None, record=RUN_RECORD):
        self.calls, self.fail, self.record, self.last_run_id = [], fail, record, None

    def run_actor(self, actor_id, run_input, max_items, max_charge_usd, timeout_s=1200):
        self.calls.append(max_charge_usd)
        if self.fail:
            raise self.fail
        self.last_run_id = "run1"
        return {"id": "run1", "status": "SUCCEEDED"}, [{}] * 10

    def run_record(self, run_id):
        return self.record

    def settled_cost(self, run, fallback_usd, n_items=None, settle_s=0):
        from src.sources.apify_client import ApifyClient
        return ApifyClient.settled_cost(self, run, fallback_usd, n_items, settle_s=0)

    def _post(self, *a, **k):
        return {}


def test_paid_run_records_actual_not_stale_usage():
    budget = CostBudget(5.0, prior_spent=0.29)
    client = FakeClient()
    _, _, cost, _ = paid_run(client, budget, "a/b", ACTOR_INFO, {"withDetails": True}, 10, "urbania 1BR", 0.5)
    assert cost == pytest.approx(0.13)
    assert budget.spent == pytest.approx(0.42) and budget.run_spent == pytest.approx(0.13)
    assert client.calls[0] == pytest.approx(0.01 + 10 * (0.012 + 0.009231))   # Apify-side ceiling = worst case


def test_unsettled_record_never_below_delivered_records():
    """Validation 2: right after the run, the record showed result 0 and USD 0.01; Apify later billed 0.07."""
    stale = {**RUN_RECORD, "usageTotalUsd": 0.01, "chargedEventCounts": {"result": 0, "apify-actor-start": 1}}
    budget = CostBudget(5.0)
    _, _, cost, basis = paid_run(FakeClient(record=stale), budget, "a/b", ACTOR_INFO, {}, 10, "urbania 1BR", 0.5)
    assert cost == pytest.approx(0.01 + 10 * 0.012) and "NOT yet settled" in basis


def test_reconcile_raises_to_settled_figure():
    budget = CostBudget(5.0, prior_spent=0.29)
    budget.charge(0.01, "urbania 1BR", "early read", "run1")
    entry = budget.ledger[0]
    assert budget.adjust(entry, 0.07, "settled") == pytest.approx(0.06)
    assert budget.adjust(entry, 0.05, "lower") == 0            # never lowered
    assert budget.spent == pytest.approx(0.36)


def test_paid_run_refuses_when_worst_case_exceeds_remaining():
    budget = CostBudget(5.0, prior_spent=4.95)
    client = FakeClient()
    with pytest.raises(BudgetStop):
        paid_run(client, budget, "a/b", ACTOR_INFO, {}, 10, "urbania 1BR", 0.5)
    assert client.calls == [] and budget.run_spent == 0


def test_account_headroom_is_also_enforced():
    assert CostBudget(5.0, prior_spent=0.3, account_headroom=0.2).remaining == pytest.approx(0.2)


def test_lost_start_request_is_charged_at_worst_case():
    budget = CostBudget(5.0)
    with pytest.raises(ApifyError):
        paid_run(FakeClient(fail=TimeoutError("read timed out")), budget, "a/b", ACTOR_INFO, {}, 5, "x", 0.5)
    assert budget.run_spent == pytest.approx(0.01 + 5 * 0.021231)


def test_unknown_cost_is_never_zero():
    with pytest.raises(ValueError):
        CostBudget(5.0).charge(None)
    no_data = {"id": "r", "pricingInfo": {"pricingModel": "PAY_PER_EVENT"}}
    budget = CostBudget(5.0)
    paid_run(FakeClient(record=no_data), budget, "a/b", ACTOR_INFO, {}, 5, "x", 0.5)
    assert budget.run_spent == pytest.approx(0.01 + 5 * 0.021231)


# --------------------------------------------------------------------------- bedroom segments
def test_one_run_per_bedroom_segment(cfg, monkeypatch):
    runs = []

    class Client:
        def __init__(self, auth, http):
            pass

        def actor_info(self, actor_id):
            return {"id": "act", **ACTOR_INFO}

        def input_schema(self, actor_id, info):
            return {k: {"type": t} for k, t in (("startUrls", "array"), ("maxListings", "integer"),
                                                 ("minBedrooms", "integer"), ("maxBedrooms", "integer"),
                                                 ("maxPrice", "integer"), ("priceCurrency", "string"),
                                                 ("withDetails", "boolean"))}

    def fake_paid_run(client, budget, actor_id, info, run_input, max_items, label, fallback):
        runs.append((label, run_input["minBedrooms"], run_input["maxBedrooms"], run_input["maxListings"], max_items))
        beds = run_input["minBedrooms"]
        return {"id": label, "status": "SUCCEEDED"}, [{**URBANIA, "bedrooms": beds, "listingId": f"{beds}{i}"}
                                                      for i in range(max_items)], 0.05, "test"

    monkeypatch.setattr(navent, "ApifyClient", Client)
    monkeypatch.setattr(navent, "paid_run", fake_paid_run)
    auth = type("A", (), {"available": True, "method": "CLOUD_CREDENTIAL", "reason": ""})()
    res = navent.collect_navent("urbania", cfg["sources"]["urbania"], cfg, None, CostBudget(5.0), "validate", auth)
    assert runs == [("urbania 1BR", 1, 1, 5, 5), ("urbania 2BR", 2, 2, 5, 5)]
    assert [lst.search_segment for lst in res.listings] == ["1BR"] * 5 + ["2BR"] * 5
    assert res.cost_usd == pytest.approx(0.10) and isinstance(res, SourceResult)

    runs.clear()   # full mode: a run never requests more than the plan returns
    navent.collect_navent("urbania", cfg["sources"]["urbania"], cfg, None, CostBudget(5.0), "full", auth, max_items=77)
    assert [r[4] for r in runs] == [10, 10]


# --------------------------------------------------------------------------- full-run rules
def test_borderline_band(cfg):
    from src.scoring.scoring import budget_class, classify
    row = dict(source="urbania", source_listing_id="1", source_url="https://urbania.pe/inmueble/x-1", operation="alquiler",
               property_type="Departamento", bedrooms=1, district="Miraflores", title="Depa", active_status="LIKELY_ACTIVE")
    assert classify({**row, "rent_usd": 1104.87}, cfg)[0] == "BORDERLINE"
    assert budget_class({**row, "rent_usd": 1104.87}, cfg)[0] == "BORDERLINE"
    assert classify({**row, "rent_usd": 1100.0}, cfg)[0] == "STRETCH"
    assert classify({**row, "rent_usd": 1112.0}, cfg)[0] == "EXCLUDED"


def test_noise_unknown_without_evidence_and_arterial_visible(cfg):
    from src.scoring.noise import assess_noise
    plain = assess_noise({"description": "Lindo departamento con cocina equipada."}, cfg)
    assert plain["noise_risk"] == "UNKNOWN" and plain["noise_label"] == "NOISE UNCERTAIN" and not plain["quietness_supported"]
    on = assess_noise({"description": "Ubicado en Miraflores, Cdra. 61 de Av. Paseo de la República) vista a la calle"}, cfg)
    assert "ON_MAJOR_ARTERIAL" in on["_noise_flags"] and on["noise_label"] == "LIKELY NOISY"
    assert on["noise_confidence"] == "LOW"
    quiet = assess_noise({"interior_view": True}, cfg)
    assert quiet["noise_label"] == "POSSIBLY QUIET" and quiet["noise_confidence"] == "LOW"


def test_hindi_translation_keeps_numbers_and_names():
    from src.reporting.i18n import language, t
    with language("hi"):
        assert t("≈ USD 934 (USD 860 rent + S/ 250 maintenance)") == "≈ USD 934 (USD 860 किराया + S/ 250 रखरखाव शुल्क)"
        assert t("listing address is on Avenida Paseo de la República — a major arterial (Vía Expresa)").startswith(
            "विज्ञापन का पता Avenida Paseo de la República पर है")
        assert t("UNKNOWN") == "जानकारी उपलब्ध नहीं" and t("STRICT_ALL_IN") == "STRICT_ALL_IN"
        assert t("https://urbania.pe/inmueble/x-1") == "https://urbania.pe/inmueble/x-1"
