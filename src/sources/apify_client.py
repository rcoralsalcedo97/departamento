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
WAIT_TIMEOUT_S = 90         # read timeout for calls that long-poll with waitForFinish=60 (client default is 30 s)


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

    def _get(self, path: str, timeout: float | None = None, **params) -> Any:
        kw = {"timeout": timeout} if timeout else {}
        r = self.http.request_json("GET", f"{API}{path}", headers=self.headers, params=params, **kw)
        if r.status_code >= 400:
            raise ApifyError(f"GET {path} → HTTP {r.status_code}: {_scrub(r.text[:300])}")
        return r.json()

    def _post(self, path: str, body: Any = None, timeout: float | None = None, **params) -> Any:
        kw = {"timeout": timeout} if timeout else {}
        r = self.http.request_json("POST", f"{API}{path}", headers=self.headers, params=params, json=body, **kw)
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

    def account_headroom_usd(self) -> tuple[float | None, str]:
        """Remaining Apify account allowance this billing cycle (the account's own hard limit)."""
        try:
            data = self._get("/users/me/limits")["data"]
            limit = float((data.get("limits") or {}).get("maxMonthlyUsageUsd"))
            used = float((data.get("current") or {}).get("monthlyUsageUsd"))
        except Exception as exc:  # noqa: BLE001
            return None, f"account limits unavailable ({type(exc).__name__})"
        cycle = data.get("monthlyUsageCycle") or {}
        return max(0.0, limit - used), (f"Apify account: USD {used:.3f} used of USD {limit:.2f} monthly limit "
                                        f"(cycle {str(cycle.get('startAt'))[:10]} → {str(cycle.get('endAt'))[:10]})")

    def run_record(self, run_id: str) -> dict:
        return self._get(f"/actor-runs/{run_id}")["data"]

    def settled_cost(self, run: dict, fallback_usd: float, settle_s: float = 20.0) -> tuple[float, str]:
        """Actual charge of a finished run, read from Apify's own run record.

        ``chargedEventCounts`` × the run's ``eventPriceUsd`` is available as soon as the run ends;
        ``usageTotalUsd`` can lag behind it for a few seconds (the first validation logged USD 0.01
        for a run that was billed USD 0.13), so the record is re-read until the two agree and the
        larger value is used. With no usable figure the conservative worst case is returned —
        an unknown cost is never treated as zero."""
        deadline = time.monotonic() + settle_s
        rec = run
        while True:
            try:
                rec = self.run_record(run["id"])
            except (ApifyError, NetworkBlocked, KeyError):
                pass
            computed, detail = charged_from_record(rec)
            reported = rec.get("usageTotalUsd")
            reported = float(reported) if reported is not None else None
            settled = computed is not None and reported is not None and reported + 5e-4 >= computed
            if settled or time.monotonic() > deadline:
                break
            time.sleep(4)
        figures = [x for x in (computed, reported) if x is not None]
        if not figures:
            return fallback_usd, f"ESTIMATED worst case USD {fallback_usd:.3f} (Apify reported no charge data)"
        return max(figures), (f"ACTUAL from Apify run record {rec.get('id')}: {detail or 'no event counts'}; "
                              f"usageTotalUsd={reported if reported is not None else 'n/a'}")

    def project_spend(self, actor_ids: set[str], since_iso: str) -> tuple[float, list[str]]:
        """Actual cumulative spend of this project: every run of the project's actors since the project
        start, priced from each run record. Raises ApifyError if the history cannot be read."""
        total, lines, offset = 0.0, [], 0
        while True:
            page = self._get("/actor-runs", desc="true", limit=250, offset=offset)["data"]
            items = page.get("items") or []
            for it in items:
                if it.get("actId") not in actor_ids or str(it.get("startedAt")) < since_iso:
                    continue
                rec = self.run_record(it["id"])
                computed, detail = charged_from_record(rec)
                reported = rec.get("usageTotalUsd")
                figures = [x for x in (computed, float(reported) if reported is not None else None) if x is not None]
                cost = max(figures) if figures else None
                if cost is None:
                    raise ApifyError(f"run {it['id']} has no charge data — cannot verify project spend")
                total += cost
                lines.append(f"{str(rec.get('startedAt'))[:19]}Z run {rec.get('id')} ({rec.get('status')}): "
                             f"USD {cost:.3f} — {detail}")
            offset += len(items)
            if not items or offset >= int(page.get("total") or 0):
                break
        return total, lines

    # ------------------------------------------------------------------ runs
    def run_actor(self, actor_id: str, run_input: dict, max_items: int, max_charge_usd: float,
                  timeout_s: int = 1200) -> tuple[dict, list[dict]]:
        self.last_run_id = None
        run = self._post(
            f"/acts/{actor_id.replace('/', '~')}/runs", run_input,
            maxItems=max_items, maxTotalChargeUsd=f"{max_charge_usd:.3f}", waitForFinish=60,
            timeout=WAIT_TIMEOUT_S,
        )["data"]
        self.last_run_id = run.get("id")
        deadline = time.monotonic() + timeout_s
        while run.get("status") not in TERMINAL:
            if time.monotonic() > deadline:
                self._post(f"/actor-runs/{run['id']}/abort")
                raise ApifyError(f"run {run['id']} exceeded {timeout_s}s and was aborted")
            run = self._get(f"/actor-runs/{run['id']}", waitForFinish=60, timeout=WAIT_TIMEOUT_S)["data"]
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


# ----------------------------------------------------------------------------- cost accounting
class BudgetStop(ApifyError):
    """A paid call was refused before launch because it could exceed the remaining budget."""


def event_prices(pricing: dict) -> dict[str, float]:
    """{event name: USD price}. Tiered prices resolve to the most expensive tier (conservative)."""
    events = ((pricing or {}).get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
    out = {}
    for name, ev in events.items():
        prices = [float(t.get("tieredEventPriceUsd") or 0) for t in (ev.get("eventTieredPricingUsd") or {}).values()]
        if ev.get("eventPriceUsd") is not None:
            prices.append(float(ev["eventPriceUsd"]))
        out[name] = max(prices) if prices else 0.0
    return out


def charged_from_record(run: dict) -> tuple[float | None, str]:
    """USD actually charged by a run = Σ chargedEventCounts × eventPriceUsd (the run's own pricing)."""
    pricing = run.get("pricingInfo") or {}
    counts = run.get("chargedEventCounts")
    if pricing.get("pricingModel") == "PAY_PER_EVENT" and isinstance(counts, dict):
        prices = event_prices(pricing)
        total = sum(float(n or 0) * prices.get(e, 0.0) for e, n in counts.items())
        detail = " + ".join(f"{e} {n}×{prices.get(e, 0):.4f}" for e, n in counts.items() if n)
        return total, detail or "no billable events"
    if pricing.get("pricingModel") == "PRICE_PER_DATASET_ITEM":
        n = ((run.get("stats") or {}).get("resultCount") or run.get("resultCount"))
        if n is not None:
            unit = float(pricing.get("pricePerUnitUsd") or 0)
            return float(n) * unit, f"{n} items × {unit:.4f}"
    return None, ""


def worst_case_cost(info: dict, max_items: int, run_input: dict, memory_mb: int = 1024) -> tuple[float | None, str]:
    """Most a run can bill: every start event plus every per-item event for ``max_items`` records, at
    the highest price tier. Opt-in AI add-ons are left out only while no ``*Ai*`` input is switched on.
    None = pricing not understood (the caller then assumes its configured conservative ceiling)."""
    pricing = (info.get("pricingInfos") or [{}])[-1]
    model = pricing.get("pricingModel", "UNKNOWN")
    if model == "PAY_PER_EVENT":
        prices = event_prices(pricing)
        events = ((pricing.get("pricingPerEvent") or {}).get("actorChargeEvents")) or {}
        ai_on = any(v is True and re.search(r"(?:^|with)Ai[A-Z]|(?:^|_)ai_", k) for k, v in run_input.items())
        start = sum(prices[n] * max(1, -(-memory_mb // 1024)) for n, e in events.items() if e.get("isOneTimeEvent"))
        per_item = {n: prices[n] for n, e in events.items()
                    if not e.get("isOneTimeEvent") and (ai_on or not n.lower().startswith("ai_"))}
        desc = f"{model}: start USD {start:.3f} + {max_items} × (" + \
            " + ".join(f"{n} {p:.4f}" for n, p in per_item.items()) + ")"
        return start + max_items * sum(per_item.values()), desc
    if model == "PRICE_PER_DATASET_ITEM":
        unit = float(pricing.get("pricePerUnitUsd") or 0)
        return unit * max_items, f"{model}: {max_items} × {unit:.4f}"
    return None, f"{model}: pricing not understood"


def paid_run(client: ApifyClient, budget, actor_id: str, info: dict, run_input: dict, max_items: int,
             label: str, fallback_usd: float, timeout_s: int = 1200) -> tuple[dict, list[dict], float, str]:
    """The only way this project launches a paid Actor run.

    1. price the worst case for this call; refuse (BudgetStop) if it could exceed what is left;
    2. launch with maxTotalChargeUsd = that worst case (a second, Apify-side ceiling);
    3. read the actual charge back from the run record and add it to the cumulative spend.
    If the run's outcome is lost mid-way, it is aborted and charged at its worst case."""
    worst, how = worst_case_cost(info, max_items, run_input)
    if worst is None:
        worst, how = fallback_usd, f"{how} — assuming conservative ceiling USD {fallback_usd:.2f}"
    if worst > budget.remaining:
        raise BudgetStop(f"{label}: worst case USD {worst:.3f} ({how}) exceeds remaining budget "
                         f"USD {budget.remaining:.3f} — not launched")
    try:
        run, items = client.run_actor(actor_id, run_input, max_items, worst, timeout_s=timeout_s)
    except Exception as exc:
        run_id = getattr(client, "last_run_id", None)
        if run_id:
            try:
                client._post(f"/actor-runs/{run_id}/abort")
            except Exception:  # noqa: BLE001 — best effort; it may already be finished
                pass
            try:
                cost, basis = client.settled_cost({"id": run_id}, worst)
            except Exception:  # noqa: BLE001
                cost, basis = worst, f"ESTIMATED worst case USD {worst:.3f} (run {run_id} outcome unknown)"
            budget.charge(cost, label, basis)
        elif not (isinstance(exc, ApifyError) and "POST" in str(exc)):
            # the start request itself failed without an HTTP refusal (e.g. a timeout): the run may exist
            budget.charge(worst, label, f"ESTIMATED worst case USD {worst:.3f} (start request failed: "
                                        f"{type(exc).__name__}; run may have started)")
        raise ApifyError(f"{label}: {type(exc).__name__}: {exc}") from exc
    cost, basis = client.settled_cost(run, worst)
    budget.charge(cost, label, basis)
    return run, items, cost, f"{basis} · pre-launch worst case USD {worst:.3f} ({how})"


def _scrub(text: str) -> str:
    return re.sub(r"apify_api_[A-Za-z0-9]+", "apify_api_***", text)
