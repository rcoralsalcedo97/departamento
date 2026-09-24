"""Minimal Apify REST client (no SDK dependency) with hard cost caps.

Token comes from APIFY_TOKEN / APIFY_API_TOKEN and is sent only in the Authorization
header — never in URLs, logs or files.
"""
from __future__ import annotations

import json
import time
from typing import Any

from ..http_client import PoliteClient

API = "https://api.apify.com/v2"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyError(RuntimeError):
    pass


class ApifyClient:
    def __init__(self, token: str, http: PoliteClient):
        self.http = http
        self.headers = {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, **params) -> Any:
        r = self.http.request_json("GET", f"{API}{path}", headers=self.headers, params=params)
        if r.status_code >= 400:
            raise ApifyError(f"GET {path} → HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def _post(self, path: str, body: Any = None, **params) -> Any:
        r = self.http.request_json("POST", f"{API}{path}", headers=self.headers, params=params, json=body)
        if r.status_code >= 400:
            raise ApifyError(f"POST {path} → HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    # ------------------------------------------------------------------ metadata
    def actor_info(self, actor_id: str) -> dict:
        return self._get(f"/acts/{actor_id.replace('/', '~')}")["data"]

    def input_schema_properties(self, actor_id: str, info: dict | None = None) -> dict | None:
        info = info or self.actor_info(actor_id)
        build_id = (((info.get("taggedBuilds") or {}).get("latest")) or {}).get("buildId")
        if not build_id:
            return None
        build = self._get(f"/actor-builds/{build_id}")["data"]
        schema = build.get("inputSchema") or (build.get("actorDefinition") or {}).get("input")
        if isinstance(schema, str):
            schema = json.loads(schema)
        return (schema or {}).get("properties")

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
                return start + sum(per_item) * max_items, f"{model}: events {sorted(events)}"
            return None, f"{model}: events {sorted(events)} (per-item price not identified)"
        if model == "FREE":
            return 0.0, "FREE (platform usage may still apply)"
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
