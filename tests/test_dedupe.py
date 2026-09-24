import pandas as pd

from src.deduplicate.dedupe import deduplicate

BASE = dict(bedrooms=2, rent_usd=900.0, total_area_m2=80.0, built_area_m2=75.0, latitude=-12.12, longitude=-77.03,
            phone="+5110000001", title="Depa 2 dorm Miraflores", address="Calle Demo 101",
            description="Hermoso departamento con vista interior y mucha luz natural, cerca al parque y al malecón. " * 2,
            image_keys=[], floor=5, maintenance_fee=None, maintenance_usd=None, rent_pen=None, maintenance_pen=None,
            active_status="LIKELY_ACTIVE")


def frame(*rows):
    return pd.DataFrame([{**BASE, **r} for r in rows])


def test_cross_posted_listing_grouped_with_all_urls(cfg):
    df = deduplicate(frame(
        dict(source="urbania", source_listing_id="1", source_url="https://urbania.pe/1", image_keys=["aaa111bbb222"]),
        dict(source="adondevivir", source_listing_id="1", source_url="https://adondevivir.com/1", rent_usd=950.0,
             image_keys=["aaa111bbb222"])), cfg)
    assert df["duplicate_group_id"].nunique() == 1
    canon = df[df["is_canonical"]].iloc[0]
    assert canon["number_of_sources"] == 2 and "adondevivir.com/1" in canon["duplicate_urls"]
    assert "PRICE_MISMATCH" in canon["dup_inconsistencies"]


def test_same_template_different_unit_not_merged(cfg):
    df = deduplicate(frame(
        dict(source="urbania", source_listing_id="1", source_url="https://u/1", address="Calle Demo 101",
             latitude=-12.12, longitude=-77.03),
        dict(source="urbania", source_listing_id="2", source_url="https://u/2", address="Calle Demo 131",
             latitude=-12.13, longitude=-77.04, rent_usd=1150.0, total_area_m2=110.0, built_area_m2=100.0)), cfg)
    assert df["duplicate_group_id"].nunique() == 2


def test_nothing_deleted(cfg):
    df = deduplicate(frame(dict(source="urbania", source_listing_id="1", source_url="https://u/1"),
                           dict(source="urbania", source_listing_id="1", source_url="https://u/1")), cfg)
    assert len(df) == 2 and df["is_canonical"].sum() == 1
