"""OpenStreetMap layers for Miraflores via the public Overpass API (one query per 30 days,
cached in data/geo/). All distances are computed locally with shapely in a metric
equirectangular projection centred on Miraflores (error < 0.1 % at this scale).
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

OVERPASS_URLS = ["https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter"]
LAT0, LON0 = -12.121, -77.030
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110574.0

MAJOR = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"}
ARTERIAL = {"secondary", "secondary_link"}


def project(lat: float, lon: float) -> tuple[float, float]:
    return (lon - LON0) * KX, (lat - LAT0) * KY


def unproject(x: float, y: float) -> tuple[float, float]:
    return y / KY + LAT0, x / KX + LON0


def build_query(bbox: list[float]) -> str:
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    return f"""[out:json][timeout:180];
(
  way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link)$"]{b};
)->.roads;
.roads out geom tags;
(
  node["amenity"~"^(nightclub|stripclub|bar|pub|restaurant|fast_food|cafe|pharmacy)$"]{b};
  way["amenity"~"^(nightclub|stripclub|bar|pub|restaurant|fast_food|cafe|pharmacy)$"]{b};
  node["leisure"="dance"]{b};
  node["shop"~"^(supermarket|convenience)$"]{b};
  way["shop"~"^(supermarket|convenience)$"]{b};
  node["highway"="bus_stop"]{b};
  node["public_transport"~"^(station|platform)$"]{b};
  node["amenity"="bus_station"]{b};
)->.pois;
.pois out center tags;
(
  way["leisure"~"^(park|garden)$"]{b};
)->.parks;
.parks out geom tags;
way["name"~"^Malec[oó]n"]{b};
out geom tags;
rel["boundary"="administrative"]["admin_level"="8"]["name"="Miraflores"]{b};
out geom tags;
"""


def fetch_overpass(cfg: dict, http, cache_path: Path, max_age_days: int = 30) -> tuple[dict | None, str]:
    """Return (overpass_json, provenance). Uses cache when fresh."""
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(cached["_fetched_at"])
        age = (datetime.now(timezone.utc) - fetched).days
        if age <= max_age_days:
            return cached, f"OSM Overpass cache from {cached['_fetched_at']} ({cached['_endpoint']})"
    query = build_query(cfg["location"]["bbox"])
    errors = []
    for url in OVERPASS_URLS:
        try:
            resp = http.request_json("POST", url, data={"data": query}, timeout=200)
            if resp.status_code == 429:
                time.sleep(30)
                resp = http.request_json("POST", url, data={"data": query}, timeout=200)
            resp.raise_for_status()
            data = resp.json()
            data["_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            data["_endpoint"] = url
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data), encoding="utf-8")
            return data, f"OSM Overpass {url} at {data['_fetched_at']} (© OpenStreetMap contributors, ODbL)"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    return None, "; ".join(errors)


@dataclass
class PoiLayer:
    names: list[str] = field(default_factory=list)
    geoms: list = field(default_factory=list)

    def add(self, name: str, geom) -> None:
        self.names.append(name)
        self.geoms.append(geom)

    def array(self):
        return np.array(self.geoms, dtype=object)


@dataclass
class OsmLayers:
    provenance: str
    major_roads: PoiLayer
    arterial_roads: PoiLayer
    nightclubs: PoiLayer
    bars: PoiLayer
    restaurants: PoiLayer
    cafes: PoiLayer
    pharmacies: PoiLayer
    supermarkets: PoiLayer
    transit: PoiLayer
    parks: PoiLayer
    malecon: PoiLayer
    boundary: Polygon | None
    road_lines_ll: list[tuple[str, list[tuple[float, float]]]] = field(default_factory=list)  # for maps
    boundary_ll: list[tuple[float, float]] = field(default_factory=list)


def _pt(el: dict):
    if "lat" in el:
        return Point(project(el["lat"], el["lon"]))
    c = el.get("center")
    return Point(project(c["lat"], c["lon"])) if c else None


def _line(geom: list[dict]):
    pts = [project(g["lat"], g["lon"]) for g in geom if g]
    return LineString(pts) if len(pts) >= 2 else None


def parse_layers(data: dict, provenance: str) -> OsmLayers:
    L = {k: PoiLayer() for k in ("major", "arterial", "night", "bars", "rest", "cafes", "pharm", "super",
                                  "transit", "parks", "malecon")}
    road_lines_ll = []
    boundary = None
    boundary_ll: list[tuple[float, float]] = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("brand") or tags.get("ref") or "(unnamed)"
        if el["type"] == "relation" and tags.get("boundary") == "administrative":
            lines = [_line(m.get("geometry", [])) for m in el.get("members", [])
                     if m.get("type") == "way" and m.get("role") in ("outer", "")]
            polys = list(polygonize(unary_union([ln for ln in lines if ln is not None])))
            if polys:
                boundary = max(polys, key=lambda p: p.area)
                boundary_ll = [unproject(x, y) for x, y in boundary.exterior.coords]
            continue
        hw = tags.get("highway")
        is_malecon = el["type"] == "way" and name.lower().startswith("malec") and "geometry" in el
        if is_malecon:
            ln = _line(el["geometry"])
            if ln is not None:
                L["malecon"].add(name, ln)
        if el["type"] == "way" and hw in MAJOR | ARTERIAL and "geometry" in el:
            ln = _line(el["geometry"])
            if ln is None:
                continue
            (L["major"] if hw in MAJOR else L["arterial"]).add(name, ln)
            road_lines_ll.append(("major" if hw in MAJOR else "arterial",
                                  [(g["lat"], g["lon"]) for g in el["geometry"]]))
            continue
        if el["type"] == "way" and tags.get("leisure") in ("park", "garden") and "geometry" in el:
            pts = [project(g["lat"], g["lon"]) for g in el["geometry"]]
            if len(pts) >= 4:
                geom = Polygon(pts)
                L["parks"].add(name, geom if geom.is_valid else geom.buffer(0))
            continue
        if is_malecon:
            continue
        geom = _pt(el)
        if geom is None:
            continue
        amenity, shop = tags.get("amenity"), tags.get("shop")
        if amenity in ("nightclub", "stripclub") or tags.get("leisure") == "dance":
            L["night"].add(name, geom)
        elif amenity in ("bar", "pub"):
            L["bars"].add(name, geom)
        elif amenity in ("restaurant", "fast_food"):
            L["rest"].add(name, geom)
        elif amenity == "cafe":
            L["cafes"].add(name, geom)
        elif amenity == "pharmacy":
            L["pharm"].add(name, geom)
        elif shop in ("supermarket", "convenience"):
            L["super"].add(name, geom)
        elif hw == "bus_stop" or tags.get("public_transport") in ("station", "platform") or amenity == "bus_station":
            L["transit"].add(name, geom)
    return OsmLayers(provenance, L["major"], L["arterial"], L["night"], L["bars"], L["rest"], L["cafes"],
                     L["pharm"], L["super"], L["transit"], L["parks"], L["malecon"], boundary,
                     road_lines_ll, boundary_ll)


def nearest(layer: PoiLayer, pt: Point) -> tuple[float | None, str | None]:
    if not layer.geoms:
        return None, None
    d = shapely.distance(pt, layer.array())
    i = int(np.argmin(d))
    return float(d[i]), layer.names[i]


def count_within(layer: PoiLayer, pt: Point, radius: float) -> tuple[int, list[str]]:
    if not layer.geoms:
        return 0, []
    d = shapely.distance(pt, layer.array())
    idx = np.where(d <= radius)[0]
    return len(idx), [layer.names[i] for i in idx]


def geo_features(layers: OsmLayers, lat: float, lon: float, cfg: dict) -> dict:
    pt = Point(project(lat, lon))
    nm = cfg["noise_model"]
    out: dict = {}
    for key, layer in (("major_road", layers.major_roads), ("arterial_road", layers.arterial_roads),
                       ("nightclub", layers.nightclubs), ("supermarket", layers.supermarkets),
                       ("pharmacy", layers.pharmacies), ("park", layers.parks), ("cafe", layers.cafes),
                       ("transit", layers.transit), ("malecon", layers.malecon)):
        d, name = nearest(layer, pt)
        out[f"dist_{key}_m"] = round(d) if d is not None else None
        out[f"{key}_name"] = name
    out["bars_within_m"], bar_names = count_within(layers.bars, pt, nm["bar_cluster"]["radius_m"])
    out["restaurants_within_m"], _ = count_within(layers.restaurants, pt, nm["restaurant_cluster"]["radius_m"])
    out["bar_names_nearby"] = ", ".join(sorted(set(bar_names))[:5])
    if layers.boundary is not None:
        inside = layers.boundary.buffer(15).contains(pt)   # 15 m tolerance for boundary drawn on street axes
        out["inside_district_polygon"] = bool(inside)
        out["dist_outside_district_m"] = 0 if inside else round(layers.boundary.exterior.distance(pt))
    else:
        out["inside_district_polygon"] = None
        out["dist_outside_district_m"] = None
    return out
