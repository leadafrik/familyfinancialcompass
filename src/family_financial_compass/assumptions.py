from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import (
    AssumptionBundle,
    DEFAULT_ASSUMPTIONS_PATH,
    assumption_bundle_from_payload,
    assumption_bundle_to_payload,
    load_assumption_bundle,
)
from .models import AssumptionAuditItem, AssumptionOverrides

_FREDDIE_MAC_URL = "https://myhome.freddiemac.com/buying/mortgage-rates"
_BLS_API_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
_BLS_RENT_SERIES_ID = "CUUR0000SEHA"
_BLS_INSURANCE_SERIES_ID = "CUUR0000SEHD"
_DEFAULT_TIMEOUT_SECONDS = 15
_ASSUMPTION_LABELS = {
    "mortgage_rate": "Mortgage rate",
    "property_tax_rate": "Property tax",
    "annual_home_insurance_cents": "Annual home insurance",
    "annual_rent_growth_rate": "Rent increase",
    "maintenance_rate": "Maintenance",
    "selling_cost_rate": "Seller closing",
    "annual_pmi_rate": "PMI",
    "buyer_closing_cost_rate": "Buyer closing costs",
}


@dataclass(frozen=True)
class LoadedAssumptionBundle:
    bundle: AssumptionBundle
    source: str
    cache_date: date


@dataclass(frozen=True)
class MortgageRateSnapshot:
    rate_date: date
    thirty_year_fixed: float
    fifteen_year_fixed: float
    source_name: str


@dataclass(frozen=True)
class BlsSeriesSnapshot:
    series_id: str
    observation_date: date
    value: float
    yoy_change: float
    source_name: str


class AssumptionStore(Protocol):
    def get_current_bundle(self) -> LoadedAssumptionBundle: ...


def _format_rate_percent(rate: float) -> str:
    return f"{rate * 100:.2f}%"


def _format_currency_value(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def _audit_value_for_field(field_name: str, value: object) -> object:
    if field_name == "annual_home_insurance_cents" and isinstance(value, int):
        return _format_currency_value(value)
    if field_name.endswith("_rate") and isinstance(value, float):
        return _format_rate_percent(value)
    return value


def apply_assumption_overrides(
    bundle: AssumptionBundle,
    overrides: AssumptionOverrides | None,
) -> AssumptionBundle:
    if overrides is None:
        return bundle

    replacement_fields = {
        field_name: value
        for field_name, value in overrides.__dict__.items()
        if value is not None
    }
    if not replacement_fields:
        return bundle

    assumptions = replace(bundle.assumptions, **replacement_fields)
    today = datetime.now(timezone.utc).date()
    audit_by_parameter = {
        item.parameter: item
        for item in bundle.audit_trail
        if item.parameter
    }
    updated_parameters: set[str] = set()
    for field_name, value in replacement_fields.items():
        audit_by_parameter[field_name] = AssumptionAuditItem(
            name=_ASSUMPTION_LABELS.get(field_name, field_name),
            parameter=field_name,
            value=_audit_value_for_field(field_name, value),
            source="User override",
            sourced_at=today.isoformat(),
            last_updated=today,
            notes="Applied as a per-scenario assumption override.",
        )
        updated_parameters.add(field_name)

    audit_trail = [
        audit_by_parameter[item.parameter]
        if item.parameter in updated_parameters
        else item
        for item in bundle.audit_trail
    ]
    for field_name in replacement_fields:
        if not any(item.parameter == field_name for item in bundle.audit_trail):
            audit_trail.append(audit_by_parameter[field_name])

    return AssumptionBundle(assumptions=assumptions, audit_trail=tuple(audit_trail))


class FileAssumptionStore:
    def __init__(self, path: Path | str = DEFAULT_ASSUMPTIONS_PATH):
        self._path = Path(path)

    def get_current_bundle(self) -> LoadedAssumptionBundle:
        bundle = load_assumption_bundle(self._path)
        if self._path.exists():
            cache_date = datetime.fromtimestamp(self._path.stat().st_mtime, tz=timezone.utc).date()
        else:
            cache_date = datetime.now(timezone.utc).date()
        return LoadedAssumptionBundle(
            bundle=bundle,
            source="file",
            cache_date=cache_date,
        )


class InMemoryAssumptionStore:
    def __init__(
        self,
        bundle: AssumptionBundle,
        source: str = "memory",
        cache_date: date | None = None,
    ) -> None:
        self._loaded = LoadedAssumptionBundle(
            bundle=bundle,
            source=source,
            cache_date=cache_date or datetime.now(timezone.utc).date(),
        )

    def set_bundle(self, bundle: AssumptionBundle, source: str | None = None) -> None:
        self._loaded = LoadedAssumptionBundle(
            bundle=bundle,
            source=source or self._loaded.source,
            cache_date=datetime.now(timezone.utc).date(),
        )

    def get_current_bundle(self) -> LoadedAssumptionBundle:
        return self._loaded


class OnlineMarketDataClient:
    def __init__(self, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_primary_mortgage_market_survey(self) -> MortgageRateSnapshot:
        request = Request(
            _FREDDIE_MAC_URL,
            headers={"User-Agent": "family-financial-compass/0.1"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            html = response.read().decode("utf-8", errors="ignore")

        date_match = re.search(
            r"Mortgage Rates as of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            html,
            re.IGNORECASE,
        )
        thirty_match = re.search(
            r"30-Yr FRM</div>\s*<div class=\"stat\">\s*([\d.]+)%",
            html,
            re.IGNORECASE,
        )
        fifteen_match = re.search(
            r"15-Yr FRM</div>\s*<div class=\"stat\">\s*([\d.]+)%",
            html,
            re.IGNORECASE,
        )
        if not (date_match and thirty_match and fifteen_match):
            raise ValueError("Freddie Mac mortgage page format did not match expected content.")

        return MortgageRateSnapshot(
            rate_date=datetime.strptime(date_match.group(1), "%B %d, %Y").date(),
            thirty_year_fixed=float(thirty_match.group(1)) / 100.0,
            fifteen_year_fixed=float(fifteen_match.group(1)) / 100.0,
            source_name="Freddie Mac PMMS",
        )

    def fetch_bls_series(self, series_id: str) -> BlsSeriesSnapshot:
        current_year = datetime.now(timezone.utc).year
        payload = {
            "seriesid": [series_id],
            "startyear": str(current_year - 2),
            "endyear": str(current_year),
        }
        request = Request(
            _BLS_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "family-financial-compass/0.1",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw_payload = json.loads(response.read().decode("utf-8"))

        series = raw_payload["Results"]["series"][0]["data"]
        monthly_rows = [
            row
            for row in series
            if isinstance(row.get("period"), str)
            and row["period"].startswith("M")
            and row["period"] != "M13"
        ]
        if not monthly_rows:
            raise ValueError(f"No monthly BLS rows returned for {series_id}.")

        latest = max(monthly_rows, key=lambda row: (int(row["year"]), int(row["period"][1:])))
        previous_year_match = next(
            (
                row
                for row in monthly_rows
                if row["year"] == str(int(latest["year"]) - 1)
                and row["period"] == latest["period"]
            ),
            None,
        )
        if previous_year_match is None:
            raise ValueError(f"Could not compute year-over-year change for {series_id}.")

        latest_value = float(latest["value"])
        previous_value = float(previous_year_match["value"])
        month = int(latest["period"][1:])
        yoy_change = (latest_value / previous_value) - 1.0
        return BlsSeriesSnapshot(
            series_id=series_id,
            observation_date=date(int(latest["year"]), month, 1),
            value=latest_value,
            yoy_change=yoy_change,
            source_name="BLS CPI",
        )


class PostgresAssumptionStore:
    def __init__(
        self,
        pool: Any,
        fallback_path: Path | str = DEFAULT_ASSUMPTIONS_PATH,
        cache_ttl_days: int = 1,
        market_data_client: OnlineMarketDataClient | None = None,
    ) -> None:
        self._pool = pool
        self._fallback_path = Path(fallback_path)
        self._cache_ttl_days = max(cache_ttl_days, 1)
        self._market_data_client = market_data_client or OnlineMarketDataClient()
        self._schema_ready = False

    def get_current_bundle(self) -> LoadedAssumptionBundle:
        today = datetime.now(timezone.utc).date()
        fallback_bundle = load_assumption_bundle(self._fallback_path)
        with self._pool.connection() as conn:
            self._ensure_schema(conn)
            current = self._fetch_active_row(conn)
            if current is None:
                try:
                    bundle, dynamic_inputs = self._build_dynamic_bundle(fallback_bundle, None)
                    source = "postgres:auto"
                except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
                    bundle, dynamic_inputs = fallback_bundle, {}
                    source = "postgres:fallback"
                return self._activate_bundle(
                    conn=conn,
                    bundle=bundle,
                    source=source,
                    cache_date=today,
                    refresh_mode="auto",
                    dynamic_inputs=dynamic_inputs,
                )

            loaded = self._row_to_loaded_bundle(current)
            if current["refresh_mode"] == "manual":
                return loaded
            if (
                current["source_label"] != "postgres:fallback"
                and (today - loaded.cache_date).days < self._cache_ttl_days
            ):
                return loaded

            try:
                refreshed_bundle, dynamic_inputs = self._build_dynamic_bundle(
                    loaded.bundle,
                    current["dynamic_inputs_json"],
                )
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
                return loaded

            return self._activate_bundle(
                conn=conn,
                bundle=refreshed_bundle,
                source="postgres:auto",
                cache_date=today,
                refresh_mode="auto",
                dynamic_inputs=dynamic_inputs,
            )

    def _ensure_schema(self, conn: Any) -> None:
        if self._schema_ready:
            return
        conn.execute(
            """
            create table if not exists assumption_sets (
                id uuid primary key default gen_random_uuid(),
                set_key text not null unique,
                model_version text not null,
                refresh_mode text not null default 'auto',
                source_label text not null,
                cache_date date not null,
                assumptions_json jsonb not null,
                audit_trail_json jsonb not null,
                dynamic_inputs_json jsonb not null default '{}'::jsonb,
                is_active boolean not null default false,
                created_at timestamptz not null default now(),
                activated_at timestamptz not null default now(),
                check (refresh_mode in ('auto', 'manual'))
            )
            """
        )
        conn.execute(
            """
            create unique index if not exists idx_assumption_sets_active
            on assumption_sets ((1))
            where is_active
            """
        )
        self._schema_ready = True

    def _fetch_active_row(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            select
                set_key,
                model_version,
                refresh_mode,
                source_label,
                cache_date,
                assumptions_json,
                audit_trail_json,
                dynamic_inputs_json
            from assumption_sets
            where is_active
            limit 1
            """
        ).fetchone()
        if row is None:
            return None
        return {
            "set_key": str(row[0]),
            "model_version": str(row[1]),
            "refresh_mode": str(row[2]),
            "source_label": str(row[3]),
            "cache_date": row[4],
            "assumptions_json": row[5],
            "audit_trail_json": row[6],
            "dynamic_inputs_json": row[7],
        }

    def _row_to_loaded_bundle(self, row: dict[str, Any]) -> LoadedAssumptionBundle:
        assumptions_json = (
            json.loads(row["assumptions_json"])
            if isinstance(row["assumptions_json"], str)
            else row["assumptions_json"]
        )
        audit_trail_json = (
            json.loads(row["audit_trail_json"])
            if isinstance(row["audit_trail_json"], str)
            else row["audit_trail_json"]
        )
        payload = {
            **assumptions_json,
            "audit_trail": audit_trail_json,
        }
        bundle = assumption_bundle_from_payload(payload)
        cache_date = row["cache_date"]
        if isinstance(cache_date, str):
            cache_date = date.fromisoformat(cache_date)
        return LoadedAssumptionBundle(
            bundle=bundle,
            source=row["source_label"],
            cache_date=cache_date,
        )

    def _activate_bundle(
        self,
        conn: Any,
        bundle: AssumptionBundle,
        source: str,
        cache_date: date,
        refresh_mode: str,
        dynamic_inputs: dict[str, object],
    ) -> LoadedAssumptionBundle:
        payload = assumption_bundle_to_payload(bundle)
        set_key = f"{refresh_mode}-{cache_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S%f')}"
        with conn.transaction():
            conn.execute("update assumption_sets set is_active = false where is_active")
            conn.execute(
                """
                insert into assumption_sets (
                    set_key,
                    model_version,
                    refresh_mode,
                    source_label,
                    cache_date,
                    assumptions_json,
                    audit_trail_json,
                    dynamic_inputs_json,
                    is_active,
                    activated_at
                )
                values (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, true, now())
                """,
                [
                    set_key,
                    bundle.assumptions.model_version,
                    refresh_mode,
                    source,
                    cache_date,
                    json.dumps({key: value for key, value in payload.items() if key != "audit_trail"}, sort_keys=True),
                    json.dumps(payload["audit_trail"], sort_keys=True),
                    json.dumps(dynamic_inputs, sort_keys=True),
                ],
            )
        return LoadedAssumptionBundle(bundle=bundle, source=source, cache_date=cache_date)

    def _build_dynamic_bundle(
        self,
        base_bundle: AssumptionBundle,
        previous_dynamic_inputs: dict[str, object] | str | None,
    ) -> tuple[AssumptionBundle, dict[str, object]]:
        dynamic_inputs = json.loads(previous_dynamic_inputs) if isinstance(previous_dynamic_inputs, str) else (previous_dynamic_inputs or {})
        mortgage = self._market_data_client.fetch_primary_mortgage_market_survey()
        rent_series = self._market_data_client.fetch_bls_series(_BLS_RENT_SERIES_ID)
        insurance_series = self._market_data_client.fetch_bls_series(_BLS_INSURANCE_SERIES_ID)

        annual_home_insurance_cents = base_bundle.assumptions.annual_home_insurance_cents
        previous_insurance = dynamic_inputs.get("insurance_series")
        if isinstance(previous_insurance, dict):
            previous_value = float(previous_insurance.get("value", 0.0))
            if previous_value > 0:
                annual_home_insurance_cents = int(
                    round(
                        annual_home_insurance_cents
                        * (insurance_series.value / previous_value)
                    )
                )

        assumptions = replace(
            base_bundle.assumptions,
            mortgage_rate=mortgage.thirty_year_fixed,
            annual_rent_growth_rate=rent_series.yoy_change,
            annual_home_insurance_cents=annual_home_insurance_cents,
            monte_carlo=replace(
                base_bundle.assumptions.monte_carlo,
                annual_rent_growth_mean=rent_series.yoy_change,
            ),
        )
        audit_trail = self._update_dynamic_audit_items(
            base_bundle.audit_trail,
            mortgage=mortgage,
            rent_series=rent_series,
            annual_home_insurance_cents=annual_home_insurance_cents,
            insurance_series=insurance_series,
        )
        refreshed_bundle = AssumptionBundle(
            assumptions=assumptions,
            audit_trail=audit_trail,
        )
        refreshed_inputs = {
            "mortgage_rate": {
                "rate_date": mortgage.rate_date.isoformat(),
                "thirty_year_fixed": mortgage.thirty_year_fixed,
                "fifteen_year_fixed": mortgage.fifteen_year_fixed,
                "source_name": mortgage.source_name,
            },
            "rent_series": {
                "series_id": rent_series.series_id,
                "observation_date": rent_series.observation_date.isoformat(),
                "value": rent_series.value,
                "yoy_change": rent_series.yoy_change,
                "source_name": rent_series.source_name,
            },
            "insurance_series": {
                "series_id": insurance_series.series_id,
                "observation_date": insurance_series.observation_date.isoformat(),
                "value": insurance_series.value,
                "yoy_change": insurance_series.yoy_change,
                "source_name": insurance_series.source_name,
            },
        }
        return refreshed_bundle, refreshed_inputs

    def _update_dynamic_audit_items(
        self,
        audit_trail: tuple[AssumptionAuditItem, ...],
        mortgage: MortgageRateSnapshot,
        rent_series: BlsSeriesSnapshot,
        annual_home_insurance_cents: int,
        insurance_series: BlsSeriesSnapshot,
    ) -> tuple[AssumptionAuditItem, ...]:
        updated: list[AssumptionAuditItem] = []
        replaced_parameters: set[str] = set()
        for item in audit_trail:
            if item.parameter == "mortgage_rate":
                updated.append(
                    AssumptionAuditItem(
                        name="30-year mortgage rate",
                        parameter="mortgage_rate",
                        value=_format_rate_percent(mortgage.thirty_year_fixed),
                        source=mortgage.source_name,
                        sourced_at=mortgage.rate_date.isoformat(),
                        last_updated=mortgage.rate_date,
                    )
                )
                replaced_parameters.add("mortgage_rate")
                continue
            if item.parameter == "annual_rent_growth_rate":
                updated.append(
                    AssumptionAuditItem(
                        name="Rent growth default",
                        parameter="annual_rent_growth_rate",
                        value=_format_rate_percent(rent_series.yoy_change),
                        source="BLS CPI Rent of primary residence",
                        sourced_at=rent_series.observation_date.isoformat(),
                        last_updated=rent_series.observation_date,
                    )
                )
                replaced_parameters.add("annual_rent_growth_rate")
                continue
            if item.parameter == "annual_home_insurance_cents":
                updated.append(
                    AssumptionAuditItem(
                        name="Annual home insurance",
                        parameter="annual_home_insurance_cents",
                        value=_format_currency_value(annual_home_insurance_cents),
                        source="BLS CPI Tenants' and household insurance + baseline premium",
                        sourced_at=insurance_series.observation_date.isoformat(),
                        last_updated=insurance_series.observation_date,
                        notes="Index-linked estimate from the most recent active assumption set.",
                    )
                )
                replaced_parameters.add("annual_home_insurance_cents")
                continue
            updated.append(item)

        if "mortgage_rate" not in replaced_parameters:
            updated.append(
                AssumptionAuditItem(
                    name="30-year mortgage rate",
                    parameter="mortgage_rate",
                    value=_format_rate_percent(mortgage.thirty_year_fixed),
                    source=mortgage.source_name,
                    sourced_at=mortgage.rate_date.isoformat(),
                    last_updated=mortgage.rate_date,
                )
            )
        if "annual_rent_growth_rate" not in replaced_parameters:
            updated.append(
                AssumptionAuditItem(
                    name="Rent growth default",
                    parameter="annual_rent_growth_rate",
                    value=_format_rate_percent(rent_series.yoy_change),
                    source="BLS CPI Rent of primary residence",
                    sourced_at=rent_series.observation_date.isoformat(),
                    last_updated=rent_series.observation_date,
                )
            )
        if "annual_home_insurance_cents" not in replaced_parameters:
            updated.append(
                AssumptionAuditItem(
                    name="Annual home insurance",
                    parameter="annual_home_insurance_cents",
                    value=_format_currency_value(annual_home_insurance_cents),
                    source="BLS CPI Tenants' and household insurance + baseline premium",
                    sourced_at=insurance_series.observation_date.isoformat(),
                    last_updated=insurance_series.observation_date,
                    notes="Index-linked estimate from the most recent active assumption set.",
                )
            )
        return tuple(updated)
