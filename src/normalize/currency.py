"""USD/PEN normalisation with explicit provenance.

One rate is fetched per run (BCRP series PD04640PD: SBS banking-system sell rate, the
same reference SUNAT publishes) and used for every conversion. Portal figures are kept
verbatim in rent_usd_published / rent_pen_published. rent_usd — the only value used for
budget, ranking, USD/m² and totals — is the USD price when the listing is priced in USD,
otherwise the PEN price ÷ that one rate (CALCULATED), so every listing is comparable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

from ..models import Listing

LIMA_TZ = timezone(timedelta(hours=-5))


@dataclass
class FxRate:
    usd_pen: float
    source: str
    timestamp: str
    live: bool

    def as_dict(self) -> dict:
        return asdict(self)


def fetch_fx(cfg: dict, client) -> tuple[FxRate, str | None]:
    """Return (rate, error). Falls back to the documented config value on any failure."""
    series = cfg["fx"]["bcrp_series"]
    end = date.today()
    start = end - timedelta(days=14)
    url = (f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{series}/json/"
           f"{start:%Y-%m-%d}/{end:%Y-%m-%d}/ing")
    error = None
    try:
        resp = client.request_json("GET", url)
        resp.raise_for_status()
        periods = resp.json().get("periods", [])
        for period in reversed(periods):
            try:
                value = float(period["values"][0])
            except (ValueError, TypeError, IndexError, KeyError):
                continue   # BCRP publishes "n.d." on holidays
            return FxRate(
                usd_pen=value,
                source=f"BCRP series {series} (SBS sell rate), period {period.get('name')} — {url}",
                timestamp=datetime.now(LIMA_TZ).isoformat(timespec="seconds"),
                live=True,
            ), None
        error = "BCRP returned no numeric value in the last 14 days"
    except Exception as exc:  # noqa: BLE001 — any failure → documented fallback
        error = f"{type(exc).__name__}: {exc}"
    fb = cfg["fx"]["fallback"]
    return FxRate(usd_pen=float(fb["usd_pen"]), source=f"FALLBACK: {fb['source']}",
                  timestamp=str(fb["timestamp"]), live=False), error


def _convert(amount: float | None, currency: str | None, rate: float) -> tuple[float | None, float | None]:
    if amount is None or currency is None:
        return None, None
    if currency == "USD":
        return round(amount * rate, 2), amount
    return amount, round(amount / rate, 2)


def apply_currency(lst: Listing, fx: FxRate) -> Listing:
    rate = fx.usd_pen
    lst.fx_rate_usd_pen = rate

    # ---- rent: published figures are preserved; rent_usd is the one comparable value
    if lst.rent_original is not None and lst.rent_currency in ("USD", "PEN"):
        if lst.rent_usd_published is None and lst.rent_usd_basis == "PUBLISHED":
            lst.rent_usd_published = lst.rent_usd
        if lst.rent_pen_published is None and lst.rent_pen_basis == "PUBLISHED":
            lst.rent_pen_published = lst.rent_pen
        pen, usd = _convert(lst.rent_original, lst.rent_currency, rate)
        if lst.rent_currency == "USD":
            # priced in USD: that price is already comparable; a published PEN figure is kept as is
            lst.rent_usd_published = lst.rent_original
            lst.rent_usd, lst.rent_usd_basis = lst.rent_original, "PUBLISHED"
            if lst.rent_pen_published is not None:
                lst.rent_pen, lst.rent_pen_basis = lst.rent_pen_published, "PUBLISHED"
            else:
                lst.rent_pen, lst.rent_pen_basis = pen, "CALCULATED"
        else:
            # priced in PEN: convert at the run's single reference rate, even when the portal also shows a
            # USD figure — those portal figures imply inconsistent rates (3.19–3.78 in the first validation)
            lst.rent_pen_published = lst.rent_original
            lst.rent_pen, lst.rent_pen_basis = lst.rent_original, "PUBLISHED"
            lst.rent_usd, lst.rent_usd_basis = usd, "CALCULATED"
        if lst.rent_usd_published and lst.rent_pen_published:
            implied = lst.rent_pen_published / rate
            lst.rent_usd_published_diff_pct = round(100 * (lst.rent_usd_published - implied) / implied, 1)

    # ---- maintenance
    if lst.maintenance_included_in_rent:
        lst.maintenance_pen = lst.maintenance_usd = 0.0
        lst.maintenance_pen_basis = lst.maintenance_usd_basis = "PUBLISHED"
    elif lst.maintenance_fee is not None and lst.maintenance_currency in ("USD", "PEN"):
        pen, usd = _convert(lst.maintenance_fee, lst.maintenance_currency, rate)
        if lst.maintenance_currency == "USD":
            lst.maintenance_usd, lst.maintenance_usd_basis = lst.maintenance_fee, "PUBLISHED"
            lst.maintenance_pen, lst.maintenance_pen_basis = pen, "CALCULATED"
        else:
            lst.maintenance_pen, lst.maintenance_pen_basis = lst.maintenance_fee, "PUBLISHED"
            lst.maintenance_usd, lst.maintenance_usd_basis = usd, "CALCULATED"

    # ---- totals (only when both parts are known — never guess maintenance)
    if lst.rent_usd is not None and lst.maintenance_usd is not None:
        lst.estimated_total_monthly_usd = round(lst.rent_usd + lst.maintenance_usd, 2)
    if lst.rent_pen is not None and lst.maintenance_pen is not None:
        lst.estimated_total_monthly_pen = round(lst.rent_pen + lst.maintenance_pen, 2)
    return lst
