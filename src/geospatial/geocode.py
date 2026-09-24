"""Address geocoding fallback (OSM Nominatim) for listings without published coordinates.

Policy-compliant: ≤ 1 request/s, identifying User-Agent, results cached, bounded to the
Miraflores bbox. Only addresses that contain a street number are geocoded; the result is
labelled GEOCODED_ADDRESS so it is never confused with portal coordinates.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

NOMINATIM = "https://nominatim.openstreetmap.org/search"


def geocodable(address: str | None) -> bool:
    return bool(address) and bool(re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{3,}.*\d{2,4}", address))


def geocode_missing(df, cfg: dict, http, cache_path: Path, max_queries: int = 150) -> tuple[int, list[str]]:
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    s, w, n, e = cfg["location"]["bbox"]
    done, errors = 0, []
    for i, row in df.iterrows():
        if row.get("latitude") == row.get("latitude") and row.get("latitude") is not None:   # not NaN
            continue
        addr = row.get("address")
        if not isinstance(addr, str) or not geocodable(addr):
            continue
        q = f"{re.sub(r'[,|]+', ' ', addr)}, Miraflores, Lima, Peru"
        if q not in cache:
            if done >= max_queries:
                break
            try:
                r = http.request_json("GET", NOMINATIM, params={
                    "q": q, "format": "jsonv2", "limit": 1, "countrycodes": "pe",
                    "viewbox": f"{w},{n},{e},{s}", "bounded": 1})
                cache[q] = r.json() if r.status_code == 200 else []
                done += 1
                import time
                time.sleep(1.1)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
                break
        hits = cache.get(q) or []
        if hits:
            h = hits[0]
            df.at[i, "latitude"], df.at[i, "longitude"] = float(h["lat"]), float(h["lon"])
            df.at[i, "coord_source"] = "GEOCODED_ADDRESS"
            df.at[i, "coord_precision"] = "STREET_NUMBER" if h.get("addresstype") in ("building", "house") \
                or h.get("type") == "house" else "STREET_LEVEL"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return done, errors
