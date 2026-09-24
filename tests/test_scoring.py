import pandas as pd

from src.scoring.noise import assess_noise
from src.scoring.scoring import classify, rank, score_all

OK = dict(source="urbania", source_listing_id="1", source_url="https://u/1", operation="Alquiler",
          property_type="Departamento", bedrooms=2, rent_usd=900.0, rent_usd_basis="PUBLISHED", district="Miraflores",
          inside_district_polygon=True, coord_precision="EXACT", latitude=-12.12, longitude=-77.03,
          built_area_m2=75.0, active_status="LIKELY_ACTIVE", dist_major_road_m=400, major_road_name="Av. X",
          dist_arterial_road_m=300, dist_nightclub_m=900, bars_within_m=0, restaurants_within_m=1,
          is_canonical=True, dist_outside_district_m=0)


def test_hard_gates(cfg):
    assert classify(OK, cfg)[0] == "PRIMARY"
    assert classify({**OK, "rent_usd": 1050.0}, cfg)[0] == "STRETCH"
    assert classify({**OK, "rent_usd": 1300.0}, cfg)[0] == "EXCLUDED"
    assert classify({**OK, "bedrooms": 0}, cfg)[0] == "EXCLUDED"
    assert classify({**OK, "bedrooms": 3}, cfg)[0] == "EXCLUDED"
    assert classify({**OK, "active_status": "INACTIVE"}, cfg)[0] == "EXCLUDED"
    assert classify({**OK, "operation": "Venta"}, cfg)[0] == "EXCLUDED"


def test_district_polygon_beats_title(cfg):
    outside = {**OK, "district": "Surquillo", "inside_district_polygon": False, "dist_outside_district_m": 120}
    cat, reasons, _ = classify(outside, cfg)
    assert cat == "NEAR_MISS_CANDIDATE" and "outside" in reasons[0]
    far = {**outside, "dist_outside_district_m": 1500}
    assert classify(far, cfg)[0] == "EXCLUDED"


def test_high_score_cannot_override_budget(cfg):
    lux = {**OK, "source_listing_id": "2", "source_url": "https://u/2", "rent_usd": 1300.0, "furnished": True,
           "security_24h": True, "gym": True, "pool": True, "built_area_m2": 120.0, "interior_view": True}
    out = rank(score_all(pd.DataFrame([OK, lux]), cfg))
    assert out.iloc[0]["source_listing_id"] == "1"
    assert out[out["source_listing_id"] == "2"]["category"].iloc[0] == "EXCLUDED"


def test_noise_model(cfg):
    loud = assess_noise({**OK, "dist_major_road_m": 20, "dist_nightclub_m": 100, "bars_within_m": 4}, cfg)
    assert loud["noise_risk"] == "HIGH" and "DIRECT_MAJOR_AVENUE" in loud["_noise_flags"]
    quiet = assess_noise({**OK, "interior_view": True, "acoustic_windows": True}, cfg)
    assert quiet["noise_risk"] == "LOW" and quiet["noise_confidence"] == "HIGH"
    blind = assess_noise({**OK, "dist_major_road_m": None, "interior_view": True}, cfg)
    assert blind["noise_confidence"] == "LOW" and "text evidence only" in blind["quietness_reason"]


def test_red_flags_and_unknowns(cfg):
    row = score_all(pd.DataFrame([{**OK, "deposit_months": 3, "minimum_contract_months": 24}]), cfg).iloc[0]
    for flag in ("UNKNOWN_MAINTENANCE", "VERY_HIGH_DEPOSIT", "LONG_MINIMUM_CONTRACT", "NO_PUBLICATION_DATE",
                 "INCOMPLETE_CONTACT"):
        assert flag in row["red_flags"]


def test_loud_units_rank_after_quiet_ones(cfg):
    loud = {**OK, "source_listing_id": "L", "source_url": "https://u/L", "dist_major_road_m": 15,
            "dist_nightclub_m": 80, "bars_within_m": 5, "furnished": True, "built_area_m2": 110.0}
    out = rank(score_all(pd.DataFrame([loud, OK]), cfg))
    assert list(out["source_listing_id"]) == ["1", "L"]
