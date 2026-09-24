"""Minimal Apify REST client (no SDK dependency) with hard cost caps.

Authentication is resolved once per run by ``resolve_apify_auth``:
  1. CLOUD_CREDENTIAL — the execution environment injects the Authorization header for
     api.apify.com (detected by an unauthenticated /users/me call that still succeeds);
  2. ENVIRONMENT_VARIABLE — APIFY_TOKEN / APIFY_API_TOKEN (from the environment or .env);
  3. NONE.
The credential is only ever placed in a request header. It is never printed, logged or
written to disk by this module.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import apify_token
from ..http_client import NetworkBlocked, PoliteClient

API = "https://api.apify.com/v2"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyError(RuntimeError):
    pass


@dataclass
class ApifyAuth:
    available: bool
    method: str                      # CLOUD_CREDENTIAL / ENVIRONMENT_VARIABLE / NONE
    reason: str = ""                 # safe, secret-free explanation
    headers: dict = field(default_factory=dict, repr=False)

    def display(self) -> list[str]:
        lines = [f"Apify authentication: {'AVAILABLE' if self.available else 'NOT AVAILABLE'}",
                 f"Method: {self.method}"]
        if self.reason:
            lines.append(f"Detail: {self.reason}")
        return lines


def resolve_apify_auth(http: PoliteClient) -> ApifyAuth:
    token = apify_token()
    method_if_blocked = "ENVIRONMENT_VARIABLE" if token else "NONE"
    try:
        r = http.request_json("GET", f"{API}/users/me")
        if r.status_code == 200 and (r.json().get("data") or {}).get("id"):
            return ApifyAuth(True, "CLOUD_CREDENTIAL", "Authorization injected by the execution environment")
    except NetworkBlocked:
        return ApifyAuth(False, method_if_blocked, "api.apify.com is unreachable from this environment "
                                                   "(network egress policy) — allow api.apify.com")
    except Exception:  # noqa: BLE001 — fall through to the token check
        pass
    if not token:
        return ApifyAuth(False, "NONE", "no APIFY_TOKEN / APIFY_API_TOKEN and no injected credential — add "
                                        "APIFY_TOKEN=... to .env (local) or configure an Apify credential")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = http.request_json("GET", f"{API}/users/me", headers=headers)
    except NetworkBlocked:
        return ApifyAuth(False, "ENVIRONMENT_VARIABLE", "api.apify.com unreachable (egress policy)")
    if r.status_code == 200:
        return ApifyAuth(True, "ENVIRONMENT_VARIABLE", "", headers)
    return ApifyAuth(False, "ENVIRONMENT_VARIABLE", f"token rejected by Apify (HTTP {r.status_code}) — "
                                                    "check or rotate APIFY_TOKEN")


# ----------------------------------------------------------------------------- adaptive input
SYNONYMS: dict[str, list[str]] = {
    "start_urls": ["startUrls", "startUrl", "searchUrls", "searchUrl", "urls", "url", "listUrls", "listingUrls"],
    "max_price": ["maxPrice", "priceMax", "price_max", "maximumPrice", "priceTo", "maxRent", "precioMaximo"],
    "currency": ["priceCurrency", "currency", "currencyId", "moneda"],
    "min_bedrooms": ["minBedrooms", "bedroomsMin", "minRooms", "roomsMin", "bedroomMin", "minDormitorios"],
    "max_bedrooms": ["maxBedrooms", "bedroomsMax", "maxRooms", "roomsMax", "bedroomMax", "maxDormitorios"],
    "operation": ["operation", "operationType", "transaction", "transactionType", "listingType", "operacion"],
    "property_type": ["propertyType", "propertyTypes", "realEstateType", "tipoInmueble"],
    "location": ["location", "locations", "district", "city", "neighborhood", "searchQuery", "query", "search"],
    "with_details": ["withDetails", "includeDetails", "scrapeDetails", "fetchDetails", "extractDetails", "details",
                     "detailed", "scrapeDetailPages"],
    "max_items": ["maxItems", "maxResults", "limit", "maxListings", "resultsLimit", "maxRecords", "maxProperties"],
}
ENUM_HINTS = {
    "operation": ["rent", "alquiler", "renta", "arriendo", "lease"],
    "property_type": ["apartment", "departamento", "depa", "apartamento", "flat"],
    "currency": ["usd", "dolar", "dólar", "us$", "2"],
}


def _prop(props: dict, key: str) -> str | None:
    lower = {p.lower(): p for p in props}
    for cand in SYNONYMS[key]:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def _enum_pick(spec: dict, hints: list[str]):
    values = spec.get("enum") or (spec.get("items") or {}).get("enum")
    if not values:
        return None
    titles = spec.get("enumTitles") or (spec.get("items") or {}).get("enumTitles") or values
    for v, t in zip(values, titles):
        blob = f"{v} {t}".lower()
        if any(h in blob for h in hints):
            return v
    return None


def build_actor_input(props: dict | None, intent: dict, max_items: int) -> tuple[dict, list[str]]:
    """Map our intent onto the actor's declared input schema. Returns (input, notes).

    With no schema available, the configured input is sent as-is (the actor ignores unknowns
    or fails loudly, which the validation gate catches)."""
    notes: list[str] = []
    if not props:
        notes.append("actor input schema unavailable — sending configured input unchanged")
        return {**intent.get("raw_input", {}), "maxItems": max_items}, notes
    out: dict[str, Any] = {}
    for key, value in intent.items():
        if key == "raw_input" or value is None:
            continue
        name = _prop(props, key)
        if not name:
            notes.append(f"no input for '{key}' in actor schema — filter re-applied after extraction")
            continue
        spec = props[name]
        typ = spec.get("type")
        if key in ENUM_HINTS:
            picked = _enum_pick(spec, ENUM_HINTS[key])
            if (spec.get("enum") or (spec.get("items") or {}).get("enum")) and picked is None:
                notes.append(f"'{name}' enum has no value matching {key}; left unset")
                continue
            value = picked if picked is not None else value
            if typ == "array":
                value = [value]
        elif key == "start_urls":
            urls = value if isinstance(value, list) else [value]
            if typ == "array":
                is_request_list = spec.get("editor") in ("requestListSources", None) and \
                    not ((spec.get("items") or {}).get("type") == "string")
                value = [{"url": u} for u in urls] if is_request_list else urls
            else:
                value = urls[0]
                if len(urls) > 1:
                    notes.append(f"'{name}' takes one URL; using the first of {len(urls)}")
        elif key == "location" and typ == "array":
            value = [value]
        elif typ == "integer":
            value = int(value)
        elif typ == "boolean":
            value = bool(value)
        out[name] = value
    if (name := _prop(props, "max_items")) and name not in out:
        out[name] = max_items
    required = [p for p, s in props.items() if s.get("required")]   # draft-style per-property flag
    missing = [p for p in required if p not in out]
    if missing:
        notes.append(f"actor marks {missing} as required but they were not set")
    return out, notes


def dataset_fields(items: list[dict], limit: int = 60) -> list[str]:
    keys: dict[str, int] = {}
    for it in items:
        for k, v in it.items():
            if v not in (None, "", [], {}):
                keys[k] = keys.get(k, 0) + 1
    return [f"{k}({n})" for k, n in sorted(keys.items(), key=lambda kv: -kv[1])[:limit]]


# ----------------------------------------------------------------------------- client
class ApifyClient:
    def __init__(self, auth: ApifyAuth, http: PoliteClient):
        if not auth.available:
            raise ApifyError(f"Apify authentication not available: {auth.reason}")
        self.http = http
        self.headers = dict(auth.headers)

    def _get(self, path: str, **params) -> Any:
        r = self.http.request_json("GET", f"{API}{path}", headers=self.headers, params=params)
        if r.status_code >= 400:
            raise ApifyError(f"GET {path} → HTTP {r.status_code}: {_scrub(r.text[:300])}")
        return r.json()

    def _post(self, path: str, body: Any = None, **params) -> Any:
        r = self.http.request_json("POST", f"{API}{path}", headers=self.headers, params=params, json=body)
        if r.status_code >= 400:
            raise ApifyError(f"POST {path} → HTTP {r.status_code}: {_scrub(r.text[:300])}")
        return r.json()

    # ------------------------------------------------------------------ metadata
    def actor_info(self, actor_id: str) -> dict:
        return self._get(f"/acts/{actor_id.replace('/', '~')}")["data"]

    def input_schema(self, actor_id: str, info: dict | None = None) -> dict | None:
        info = info or self.actor_info(actor_id)
        build_id = (((info.get("taggedBuilds") or {}).get("latest")) or {}).get("buildId")
        if not build_id:
            return None
        build = self._get(f"/actor-builds/{build_id}")["data"]
        schema = build.get("inputSchema") or (build.get("actorDefinition") or {}).get("input")
        if isinstance(schema, str):
            schema = json.loads(schema)
        if not schema:
            return None
        props = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req in props:
                props[req] = {**props[req], "required": True}
        return props

    def monthly_usage_usd(self) -> float | None:
        try:
            data = self._get("/users/me/limits")["data"]
            return float((data.get("current") or {}).get("monthlyUsageUsd"))
        except Exception:  # noqa: BLE001 — informational only
            return None

    @staticmethod
    def estimate_cost(info: dict, max_items: int) -> tuple[float | None, str]:
        pricing = (info.get("pricingInfos") or [{}])[-1]
        model = pricing.get("pricingModel", "UNKNOWN")
        if model == "PRICE_PER_DATASET_ITEM":
            unit = float(pricing.get("pricePerUnitUsd") or 0)
            return unit * max_items, f"{model}: ${unit:.4f}/item"
        if model == "PAY_PER_EVENT":
            events = ((pricing.get("pricingPerEvent") or {}).get("actorChargeEvents")) or {}
            per_item = [float(e.get("eventPriceUsd") or 0) for name, e in events.items()
                        if any(k in name.lower() for k in ("result", "item", "listing", "detail", "property"))]
            start = sum(float(e.get("eventPriceUsd") or 0) for name, e in events.items() if "start" in name.lower())
            if per_item:
                return start + sum(per_item) * max_items, (f"{model}: " + ", ".join(
                    f"{n}=${float(e.get('eventPriceUsd') or 0):.4f}" for n, e in events.items()))
            return None, f"{model}: events {sorted(events)} (per-item price not identified)"
        if model == "FREE":
            return 0.0, "FREE (platform usage may still apply)"
        if model == "FLAT_PRICE_PER_MONTH":
            return None, f"{model}: rental ${pricing.get('pricePerUnitUsd')}/month (trial may apply)"
        return None, model

    # ------------------------------------------------------------------ runs
    def run_actor(self, actor_id: str, run_input: dict, max_items: int, max_charge_usd: float,
                  timeout_s: int = 1200) -> tuple[dict, list[dict]]:
        run = self._post(
            f"/acts/{actor_id.replace('/', '~')}/runs", run_input,
            maxItems=max_items, maxTotalChargeUsd=f"{max_charge_usd:.2f}", waitForFinish=60,
        )["data"]
        deadline = time.monotonic() + timeout_s
        while run.get("status") not in TERMINAL:
            if time.monotonic() > deadline:
                self._post(f"/actor-runs/{run['id']}/abort")
                raise ApifyError(f"run {run['id']} exceeded {timeout_s}s and was aborted")
            run = self._get(f"/actor-runs/{run['id']}", waitForFinish=60)["data"]
        items: list[dict] = []
        if run.get("defaultDatasetId"):
            offset = 0
            while len(items) < max_items:
                batch = self._get(f"/datasets/{run['defaultDatasetId']}/items", clean="true",
                                  format="json", offset=offset, limit=min(250, max_items - len(items)))
                if not batch:
                    break
                items.extend(batch)
                offset += len(batch)
        return run, items


def _scrub(text: str) -> str:
    return re.sub(r"apify_api_[A-Za-z0-9]+", "apify_api_***", text)
