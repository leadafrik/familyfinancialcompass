from __future__ import annotations

import csv
import dataclasses
import io
import json
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

_FREDDIE_MAC_URL = "https://www.freddiemac.com/pmms/docs/PMMS_history.csv"
_BLS_API_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
_BLS_RENT_SERIES_ID = "CUUR0000SEHA"
_BLS_INSURANCE_SERIES_ID = "CUUR0000SEHD"
_DEFAULT_TIMEOUT_SECONDS = 15
_DYNAMIC_SOURCE_KEYS = frozenset({"mortgage_rate", "rent_series", "insurance_series"})
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
        field_.name: getattr(overrides, field_.name)
        for field_ in dataclasses.fields(overrides)
        if getattr(overrides, field_.name) is not None
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
    def __init__(
        self,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        bls_api_key: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.bls_api_key = bls_api_key

    def fetch_primary_mortgage_market_survey(self) -> MortgageRateSnapshot:
        request = Request(
            _FREDDIE_MAC_URL,
            headers={"User-Agent": "family-financial-compass/0.1"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="ignore")

        reader = csv.DictReader(io.StringIO(raw))
        best_row: dict | None = None
        best_date: date | None = None
        for row in reader:
            pmms30 = row.get("pmms30", "").strip()
            pmms15 = row.get("pmms15", "").strip()
            raw_date = row.get("date", "").strip()
            if not (pmms30 and pmms15 and raw_date):
                continue
            try:
                row_date = datetime.strptime(raw_date, "%m/%d/%Y").date()
            except ValueError:
                continue
            if best_date is None or row_date > best_date:
                best_date = row_date
                best_row = row

        if best_row is None or best_date is None:
            raise ValueError("Freddie Mac PMMS CSV contained no usable rows.")

        return MortgageRateSnapshot(
            rate_date=best_date,
            thirty_year_fixed=float(best_row["pmms30"]) / 100.0,
            fifteen_year_fixed=float(best_row["pmms15"]) / 100.0,
            source_name="Freddie Mac PMMS",
        )

    def fetch_bls_series(self, series_id: str) -> BlsSeriesSnapshot:
        current_year = datetime.now(timezone.utc).year
        payload = {
            "seriesid": [series_id],
            "startyear": str(current_year - 3),
            "endyear": str(current_year),
        }
        if self.bls_api_key:
            payload["registrationkey"] = self.bls_api_key
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
        bls_api_key: str | None = None,
    ) -> None:
        self._pool = pool
        self._fallback_path = Path(fallback_path)
        self._cache_ttl_days = max(cache_ttl_days, 1)
        self._market_data_client = market_data_client or OnlineMarketDataClient(bls_api_key=bls_api_key)
        self._schema_ready = False

    def get_current_bundle(self) -> LoadedAssumptionBundle:
        today = datetime.now(timezone.utc).date()
        with self._pool.connection() as conn:
            self._ensure_schema(conn)
            current = self._fetch_active_row(conn)
            if current is None:
                fallback_bundle = load_assumption_bundle(self._fallback_path)
                try:
                    bundle, dynamic_inputs = self._build_dynamic_bundle(fallback_bundle, None)
                    source = self._dynamic_source_label(dynamic_inputs)
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
                fallback_bundle = load_assumption_bundle(self._fallback_path)
                return self._activate_bundle(
                    conn=conn,
                    bundle=fallback_bundle,
                    source="postgres:fallback",
                    cache_date=today,
                    refresh_mode="auto",
                    dynamic_inputs={},
                )

            return self._activate_bundle(
                conn=conn,
                bundle=refreshed_bundle,
                source=self._dynamic_source_label(dynamic_inputs),
                cache_date=today,
                refresh_mode="auto",
                dynamic_inputs=dynamic_inputs,
            )

    def _ensure_schema(self, conn: Any) -> None:
        if self._schema_ready:
            return
        with conn.transaction():
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

    def _dynamic_source_label(self, dynamic_inputs: dict[str, object]) -> str:
        return "postgres:auto" if _DYNAMIC_SOURCE_KEYS.issubset(dynamic_inputs) else "postgres:partial"

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
        mortgage: MortgageRateSnapshot | None = None
        updated_mortgage_rate = base_bundle.assumptions.mortgage_rate
        try:
            mortgage = self._market_data_client.fetch_primary_mortgage_market_survey()
            updated_mortgage_rate = mortgage.thirty_year_fixed
        except (HTTPError, URLError, TimeoutError, ValueError):
            mortgage = None

        rent_series: BlsSeriesSnapshot | None = None
        updated_rent_growth = base_bundle.assumptions.annual_rent_growth_rate
        try:
            rent_series = self._market_data_client.fetch_bls_series(_BLS_RENT_SERIES_ID)
            updated_rent_growth = rent_series.yoy_change
        except (HTTPError, URLError, TimeoutError, ValueError):
            rent_series = None

        insurance_snapshot: BlsSeriesSnapshot | None = None
        audit_insurance_series: BlsSeriesSnapshot | None = None
        annual_home_insurance_cents = base_bundle.assumptions.annual_home_insurance_cents
        try:
            insurance_snapshot = self._market_data_client.fetch_bls_series(_BLS_INSURANCE_SERIES_ID)
            previous_insurance = dynamic_inputs.get("insurance_series")
            if isinstance(previous_insurance, dict):
                previous_value = float(previous_insurance.get("value", 0.0))
                if previous_value > 0:
                    adjusted_value = int(
                        round(
                            annual_home_insurance_cents
                            * (insurance_snapshot.value / previous_value)
                        )
                    )
                    static_baseline = load_assumption_bundle(self._fallback_path).assumptions.annual_home_insurance_cents
                    floor = int(static_baseline * 0.50)
                    ceiling = int(static_baseline * 3.00)
                    annual_home_insurance_cents = max(floor, min(ceiling, adjusted_value))
                    audit_insurance_series = insurance_snapshot
        except (HTTPError, URLError, TimeoutError, ValueError):
            insurance_snapshot = None
            audit_insurance_series = None

        assumptions = replace(
            base_bundle.assumptions,
            mortgage_rate=updated_mortgage_rate,
            annual_rent_growth_rate=updated_rent_growth,
            annual_home_insurance_cents=annual_home_insurance_cents,
            monte_carlo=replace(
                base_bundle.assumptions.monte_carlo,
                annual_rent_growth_mean=updated_rent_growth,
            ),
        )
        audit_trail = self._update_dynamic_audit_items(
            base_bundle.audit_trail,
            mortgage=mortgage,
            rent_series=rent_series,
            annual_home_insurance_cents=annual_home_insurance_cents,
            insurance_series=audit_insurance_series,
        )
        refreshed_bundle = AssumptionBundle(
            assumptions=assumptions,
            audit_trail=audit_trail,
        )
        refreshed_inputs: dict[str, object] = {}
        if mortgage is not None:
            refreshed_inputs["mortgage_rate"] = {
                "rate_date": mortgage.rate_date.isoformat(),
                "thirty_year_fixed": mortgage.thirty_year_fixed,
                "fifteen_year_fixed": mortgage.fifteen_year_fixed,
                "source_name": mortgage.source_name,
            }
        if rent_series is not None:
            refreshed_inputs["rent_series"] = {
                "series_id": rent_series.series_id,
                "observation_date": rent_series.observation_date.isoformat(),
                "value": rent_series.value,
                "yoy_change": rent_series.yoy_change,
                "source_name": rent_series.source_name,
            }
        if insurance_snapshot is not None:
            refreshed_inputs["insurance_series"] = {
                "series_id": insurance_snapshot.series_id,
                "observation_date": insurance_snapshot.observation_date.isoformat(),
                "value": insurance_snapshot.value,
                "yoy_change": insurance_snapshot.yoy_change,
                "source_name": insurance_snapshot.source_name,
            }
        return refreshed_bundle, refreshed_inputs

    def _update_dynamic_audit_items(
        self,
        audit_trail: tuple[AssumptionAuditItem, ...],
        mortgage: MortgageRateSnapshot | None,
        rent_series: BlsSeriesSnapshot | None,
        annual_home_insurance_cents: int,
        insurance_series: BlsSeriesSnapshot | None,
    ) -> tuple[AssumptionAuditItem, ...]:
        updated: list[AssumptionAuditItem] = []
        replaced_parameters: set[str] = set()
        for item in audit_trail:
            if item.parameter == "mortgage_rate" and mortgage is not None:
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
            if item.parameter == "annual_rent_growth_rate" and rent_series is not None:
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
            if item.parameter == "annual_home_insurance_cents" and insurance_series is not None:
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

        if mortgage is not None and "mortgage_rate" not in replaced_parameters:
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
        if rent_series is not None and "annual_rent_growth_rate" not in replaced_parameters:
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
        if insurance_series is not None and "annual_home_insurance_cents" not in replaced_parameters:
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
