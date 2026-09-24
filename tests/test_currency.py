from src.models import Listing
from src.normalize.currency import apply_currency


def test_usd_published_pen_calculated(fx):
    lst = apply_currency(Listing(source="t", rent_original=900, rent_currency="USD"), fx)
    assert lst.rent_usd == 900 and lst.rent_usd_basis == "PUBLISHED"
    assert lst.rent_pen == 3060 and lst.rent_pen_basis == "CALCULATED"
    assert lst.estimated_total_monthly_usd is None       # maintenance unknown → no invented total


def test_pen_published_with_maintenance(fx):
    lst = apply_currency(Listing(source="t", rent_original=3400, rent_currency="PEN",
                                 maintenance_fee=340, maintenance_currency="PEN"), fx)
    assert lst.rent_usd == 1000 and lst.rent_usd_basis == "CALCULATED"
    assert lst.maintenance_usd == 100 and lst.maintenance_pen_basis == "PUBLISHED"
    assert lst.estimated_total_monthly_usd == 1100


def test_both_currencies_published_are_kept(fx):
    lst = apply_currency(Listing(source="t", rent_original=950, rent_currency="USD", rent_pen=3300,
                                 rent_pen_basis="PUBLISHED"), fx)
    assert lst.rent_pen == 3300 and lst.rent_pen_basis == "PUBLISHED"


def test_maintenance_included(fx):
    lst = apply_currency(Listing(source="t", rent_original=800, rent_currency="USD",
                                 maintenance_included_in_rent=True), fx)
    assert lst.estimated_total_monthly_usd == 800
