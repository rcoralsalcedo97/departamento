"""Cross-portal duplicate grouping.

Nothing is deleted. Each record receives a duplicate_group_id; one canonical record per
group is used for ranking and carries duplicate_sources / duplicate_urls /
number_of_sources plus any inconsistencies found between the copies.
"""
from __future__ import annotations

import math
import re
from urllib.parse import urlparse

import pandas as pd
from rapidfuzz import fuzz

from ..normalize.text_signals import fold

SOURCE_PRIORITY = {"urbania": 0, "adondevivir": 1, "mercadolibre": 2, "manual": 3}
NAVENT = {"urbania", "adondevivir"}


def norm_url(url: str | None) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    p = urlparse(url)
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}".lower()


def norm_address(addr: str | None) -> str:
    if not isinstance(addr, str):
        return ""
    a = fold(addr)
    a = re.sub(r"\b(avenida|av\.?)\b", "av", a)
    a = re.sub(r"\b(calle|jr\.?|jiron|psje\.?|pasaje)\b", "", a)
    a = re.sub(r"miraflores|lima|peru|\bmir\b", "", a)
    return re.sub(r"[^a-z0-9 ]", " ", a).split("|")[0].strip()


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _num(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _close(a, b, tol) -> bool | None:
    a, b = _num(a), _num(b)
    if a is None or b is None or max(a, b) == 0:
        return None
    return abs(a - b) / max(a, b) <= tol


def _area_pair(a: pd.Series, b: pd.Series) -> tuple[float | None, float | None]:
    """Compare like with like: built vs built, else total vs total, else whatever exists."""
    for key in ("built_area_m2", "total_area_m2"):
        x, y = _num(a.get(key)), _num(b.get(key))
        if x and y:
            return x, y
    return (_num(a.get("built_area_m2")) or _num(a.get("total_area_m2")),
            _num(b.get("built_area_m2")) or _num(b.get("total_area_m2")))


def _street_numbers(addr: str) -> set[str]:
    return set(re.findall(r"\b\d{2,5}\b", addr))


def pair_score(a: pd.Series, b: pd.Series, cfg: dict) -> tuple[float, list[str], bool]:
    """Return (score, evidence, anchored). A merge needs score ≥ threshold AND a hard identity anchor
    (portal id, shared photo, coordinates within coord_match_m, or the same numbered address);
    similar wording alone never merges two listings — agents reuse descriptions across units."""
    d = cfg["dedupe"]
    why: list[str] = []
    ua, ub = norm_url(a.get("source_url")), norm_url(b.get("source_url"))
    if ua and ua == ub:
        return 1.0, ["same URL"], True
    if a["source"] == b["source"] and a.get("source_listing_id") and a.get("source_listing_id") == b.get("source_listing_id"):
        return 1.0, ["same source id"], True
    ba, bb = _num(a.get("bedrooms")), _num(b.get("bedrooms"))
    if ba is not None and bb is not None and ba != bb:
        return 0.0, ["bedrooms differ"], False

    s, anchored = 0.0, False
    if a["source"] in NAVENT and b["source"] in NAVENT and a["source"] != b["source"] \
            and a.get("source_listing_id") and a.get("source_listing_id") == b.get("source_listing_id"):
        s += 0.9
        anchored = True
        why.append("same Navent posting id")

    la, lo, lb, lob = (_num(a.get("latitude")), _num(a.get("longitude")),
                       _num(b.get("latitude")), _num(b.get("longitude")))
    if None not in (la, lo, lb, lob):
        dist = haversine_m(la, lo, lb, lob)
        if dist <= d["coord_match_m"]:
            s += 0.30
            anchored = True
            why.append(f"coords {dist:.0f} m apart")
        elif dist <= 100:
            s += 0.10
        elif dist > 600:
            s -= 0.50

    area_a, area_b = _area_pair(a, b)
    c = _close(area_a, area_b, d["area_tolerance"])
    if c is True:
        s += 0.20
        why.append("same area")
    elif c is False and not _close(area_a, area_b, 0.15):
        s -= 0.30

    c = _close(a.get("rent_usd"), b.get("rent_usd"), d["price_tolerance"])
    if c is True:
        s += 0.15
        why.append("same price")
    elif c is False and not _close(a.get("rent_usd"), b.get("rent_usd"), 0.15):
        s -= 0.30

    c = _close(a.get("bathrooms"), b.get("bathrooms"), 0.0)
    if c is True:
        s += 0.05
        why.append("same bathrooms")
    elif c is False:
        s -= 0.30

    ma, mb = _num(a.get("maintenance_pen")), _num(b.get("maintenance_pen"))
    c = _close(ma, mb, d["price_tolerance"])
    if c is True:
        s += 0.05
        why.append("same maintenance")
    elif c is False and not _close(ma, mb, 0.15):
        s -= 0.15

    if a.get("advertiser_key") and a.get("advertiser_key") == b.get("advertiser_key"):
        s += 0.10
        why.append("same advertiser")

    if a.get("phone") and a.get("phone") == b.get("phone"):
        s += 0.25
        why.append("same phone")

    ta, tb = a.get("title") or "", b.get("title") or ""
    if ta and tb and fuzz.token_set_ratio(fold(ta), fold(tb)) >= d["title_ratio"]:
        s += 0.10
        why.append("similar title")

    da, db = (a.get("description") or "")[:800], (b.get("description") or "")[:800]
    if len(da) > 80 and len(db) > 80:
        r = fuzz.token_set_ratio(fold(da), fold(db))
        if r >= d["description_ratio"]:
            s += 0.30
            why.append(f"description {r:.0f}% similar")

    na, nb = norm_address(a.get("address")), norm_address(b.get("address"))
    nums_a, nums_b = _street_numbers(na), _street_numbers(nb)
    if nums_a and nums_b:
        if nums_a & nums_b and fuzz.token_set_ratio(na, nb) >= 90:
            s += 0.20
            anchored = True
            why.append("same numbered address")
        elif not nums_a & nums_b:
            s -= 0.20

    ka, kb = set(a.get("image_keys") or []), set(b.get("image_keys") or [])
    if ka & kb:
        s += 0.40
        anchored = True
        why.append("shared photo id")

    fa, fb = _num(a.get("floor")), _num(b.get("floor"))
    if fa is not None and fb is not None:
        s += 0.05 if fa == fb else -0.15
    return s, why, anchored


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _completeness(row: pd.Series) -> int:
    keys = ["latitude", "total_area_m2", "maintenance_fee", "description", "publication_date", "phone",
            "floor", "furnished", "bathrooms", "address", "image_count"]
    return sum(1 for k in keys if row.get(k) not in (None, "") and not (isinstance(row.get(k), float) and math.isnan(row.get(k))))


def deduplicate(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    n = len(df)
    uf = _UF(n)
    threshold = cfg["dedupe"]["match_threshold"]
    evidence: dict[int, list[str]] = {i: [] for i in range(n)}
    possible: dict[int, set[int]] = {i: set() for i in range(n)}

    for i in range(n):
        a = df.iloc[i]
        for j in range(i + 1, n):
            b = df.iloc[j]
            pa, pb = _num(a.get("rent_usd")), _num(b.get("rent_usd"))
            if pa and pb and abs(pa - pb) / max(pa, pb) > 0.35 and norm_url(a.get("source_url")) != norm_url(b.get("source_url")):
                continue   # cheap blocking: very different prices are not the same flat
            score, why, anchored = pair_score(a, b, cfg)
            if score >= threshold and anchored:
                uf.union(i, j)
                evidence[i].append(f"≈{b['source']}:{b.get('source_listing_id')} ({', '.join(why)})")
                evidence[j].append(f"≈{a['source']}:{a.get('source_listing_id')} ({', '.join(why)})")
            elif score >= threshold - 0.15 or (score >= threshold and not anchored):
                possible[i].add(j)
                possible[j].add(i)

    roots = [uf.find(i) for i in range(n)]
    df["_root"] = roots
    group_ids = {r: f"G{k + 1:04d}" for k, r in enumerate(dict.fromkeys(roots))}
    df["duplicate_group_id"] = [group_ids[r] for r in roots]
    df["dedupe_evidence"] = ["; ".join(evidence[i]) for i in range(n)]
    df["is_canonical"] = False
    df["duplicate_sources"] = ""
    df["duplicate_urls"] = ""
    df["number_of_sources"] = 1
    df["number_of_records"] = 1
    df["dup_inconsistencies"] = ""
    df["fields_filled_from_duplicates"] = ""
    df["possible_duplicate_of"] = ""

    for gid, idx in df.groupby("duplicate_group_id").groups.items():
        idx = list(idx)
        members = df.loc[idx]
        order = sorted(idx, key=lambda k: (-_completeness(df.loc[k]), SOURCE_PRIORITY.get(df.loc[k, "source"], 9)))
        canon = order[0]
        df.loc[canon, "is_canonical"] = True
        df.at[canon, "duplicate_sources"] = "; ".join(sorted(set(members["source"])))
        df.at[canon, "duplicate_urls"] = "; ".join(u for u in members["source_url"].dropna().unique())
        df.at[canon, "number_of_sources"] = members["source"].nunique()
        df.at[canon, "number_of_records"] = len(idx)
        if len(idx) > 1:
            issues = []
            prices = members["rent_usd"].dropna().astype(float)
            if len(prices) > 1 and prices.max() / max(prices.min(), 1) > 1.05:
                issues.append(f"PRICE_MISMATCH ({prices.min():.0f}–{prices.max():.0f} USD)")
            areas = members["total_area_m2"].dropna().astype(float)
            if len(areas) > 1 and areas.max() / max(areas.min(), 1) > 1.10:
                issues.append(f"AREA_MISMATCH ({areas.min():.0f}–{areas.max():.0f} m²)")
            beds = members["bedrooms"].dropna().unique()
            if len(beds) > 1:
                issues.append(f"BEDROOM_MISMATCH ({sorted(beds)})")
            if "active_status" in members and (members["active_status"] == "INACTIVE").any() \
                    and (members["active_status"] != "INACTIVE").any():
                issues.append("STATUS_MISMATCH (one copy marked inactive)")
            lat = members["latitude"].dropna().astype(float)
            if len(lat) > 1:
                pts = members[["latitude", "longitude"]].dropna().astype(float).values
                spread = max(haversine_m(p[0], p[1], q[0], q[1]) for p in pts for q in pts)
                if spread > 150:
                    issues.append(f"COORD_MISMATCH ({spread:.0f} m apart)")
            addrs = [norm_address(x) for x in members["address"].dropna() if norm_address(x)]
            if len(addrs) > 1 and min(fuzz.token_set_ratio(addrs[0], x) for x in addrs[1:]) < 70:
                issues.append("ADDRESS_MISMATCH")
            df.at[canon, "dup_inconsistencies"] = "; ".join(issues)
            # backfill UNKNOWN canonical fields from copies (never overwrite a known value)
            filled = []
            for col in ("latitude", "longitude", "coord_source", "coord_precision", "total_area_m2",
                        "built_area_m2", "maintenance_fee", "maintenance_currency", "maintenance_pen",
                        "maintenance_usd", "maintenance_pen_basis", "maintenance_usd_basis", "floor", "phone",
                        "whatsapp", "publication_date", "furnished", "deposit_months", "minimum_contract_months"):
                if col not in df.columns:
                    continue
                cur = df.at[canon, col]
                if cur is None or (isinstance(cur, float) and math.isnan(cur)):
                    for k in order[1:]:
                        val = df.at[k, col]
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            df.at[canon, col] = val
                            filled.append(f"{col}←{df.at[k, 'source']}")
                            break
            df.at[canon, "fields_filled_from_duplicates"] = "; ".join(filled)
            # totals are recomputed from the canonical rent, never copied from another portal
            if _num(df.at[canon, "rent_usd"]) is not None and _num(df.at[canon, "maintenance_usd"]) is not None:
                df.at[canon, "estimated_total_monthly_usd"] = round(
                    float(df.at[canon, "rent_usd"]) + float(df.at[canon, "maintenance_usd"]), 2)
            if _num(df.at[canon, "rent_pen"]) is not None and _num(df.at[canon, "maintenance_pen"]) is not None:
                df.at[canon, "estimated_total_monthly_pen"] = round(
                    float(df.at[canon, "rent_pen"]) + float(df.at[canon, "maintenance_pen"]), 2)
        poss = {df.loc[j, "duplicate_group_id"] for i in idx for j in possible[i]} - {gid}
        df.at[canon, "possible_duplicate_of"] = "; ".join(sorted(poss))
    return df.drop(columns="_root")
