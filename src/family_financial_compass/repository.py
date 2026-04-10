from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Protocol

from .models import ScenarioOutputRecord, ScenarioRecord


@dataclass(frozen=True)
class ScenarioBundle:
    scenario: ScenarioRecord
    output: ScenarioOutputRecord


@dataclass(frozen=True)
class ScenarioPage:
    items: tuple[ScenarioBundle, ...]
    next_cursor: str | None


class ScenarioRepository(Protocol):
    def save(self, scenario: ScenarioRecord, output: ScenarioOutputRecord) -> ScenarioBundle: ...

    def get(self, scenario_id: str) -> ScenarioBundle | None: ...

    def list_for_user(self, user_id: str, limit: int, cursor: str | None = None) -> ScenarioPage: ...

    def ping(self) -> None: ...


def _parse_created_at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _encode_cursor(created_at: str, scenario_id: str) -> str:
    raw = f"{created_at}|{scenario_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at, scenario_id = raw.rsplit("|", 1)
    return created_at, scenario_id


def _bundle_sort_key(bundle: ScenarioBundle) -> tuple[datetime, str]:
    return (_parse_created_at(bundle.scenario.created_at), bundle.scenario.id)


def _output_summary_fields(output: ScenarioOutputRecord) -> tuple[float | None, int | None, int | None]:
    monte_carlo = output.output_blob.get("monte_carlo", {})
    probability = monte_carlo.get("probability_buy_beats_rent")
    median_advantage = monte_carlo.get("median_terminal_advantage_cents")
    median_break_even = monte_carlo.get("median_break_even_month")
    return (
        float(probability) if probability is not None else None,
        int(median_advantage) if median_advantage is not None else None,
        int(median_break_even) if median_break_even is not None else None,
    )


def _normalize_json(value: Any) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _normalize_timestamp(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class FileScenarioRepository:
    def __init__(self, base_dir: Path):
        self.storage_dir = Path(base_dir) / "scenarios"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @property
    def storage_target(self) -> str:
        return str(self.storage_dir)

    def ping(self) -> None:
        if not self.storage_dir.is_dir():
            raise RuntimeError(f"Scenario storage directory is not accessible: {self.storage_dir}")

    def save(self, scenario: ScenarioRecord, output: ScenarioOutputRecord) -> ScenarioBundle:
        if scenario.idempotency_key is not None:
            existing = self._find_by_idempotency_key(
                user_id=scenario.user_id,
                idempotency_key=scenario.idempotency_key,
            )
            if existing is not None:
                return existing

        payload = {
            "scenario": scenario.__dict__,
            "output": output.__dict__,
        }
        target_path = self.storage_dir / f"{scenario.id}.json"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.storage_dir,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_path = Path(temp_file.name)
        os.replace(temp_path, target_path)
        return ScenarioBundle(scenario=scenario, output=output)

    def get(self, scenario_id: str) -> ScenarioBundle | None:
        target_path = self.storage_dir / f"{scenario_id}.json"
        if not target_path.exists():
            return None
        payload = json.loads(target_path.read_text(encoding="utf-8"))
        return ScenarioBundle(
            scenario=ScenarioRecord(**payload["scenario"]),
            output=ScenarioOutputRecord(**payload["output"]),
        )

    def list_for_user(self, user_id: str, limit: int, cursor: str | None = None) -> ScenarioPage:
        bundles = [
            bundle
            for bundle in self._iter_bundles()
            if bundle.scenario.user_id == user_id
        ]
        bundles.sort(key=_bundle_sort_key, reverse=True)
        filtered = self._apply_cursor(bundles, cursor)
        page_items = filtered[: limit + 1]
        has_more = len(page_items) > limit
        items = tuple(page_items[:limit])
        next_cursor = None
        if has_more and items:
            last = items[-1].scenario
            next_cursor = _encode_cursor(last.created_at, last.id)
        return ScenarioPage(items=items, next_cursor=next_cursor)

    def _iter_bundles(self) -> list[ScenarioBundle]:
        bundles: list[ScenarioBundle] = []
        for path in self.storage_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            bundles.append(
                ScenarioBundle(
                    scenario=ScenarioRecord(**payload["scenario"]),
                    output=ScenarioOutputRecord(**payload["output"]),
                )
            )
        return bundles

    def _find_by_idempotency_key(self, user_id: str, idempotency_key: str) -> ScenarioBundle | None:
        for bundle in self._iter_bundles():
            if bundle.scenario.user_id == user_id and bundle.scenario.idempotency_key == idempotency_key:
                return bundle
        return None

    def _apply_cursor(self, bundles: list[ScenarioBundle], cursor: str | None) -> list[ScenarioBundle]:
        if cursor is None:
            return bundles
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        cursor_key = (_parse_created_at(cursor_created_at), cursor_id)
        return [
            bundle
            for bundle in bundles
            if _bundle_sort_key(bundle) < cursor_key
        ]


class PostgresScenarioRepository:
    def __init__(
        self,
        database_url: str | None = None,
        min_pool_size: int = 1,
        max_pool_size: int = 10,
        connect_timeout_seconds: float = 5.0,
        pool: Any | None = None,
    ) -> None:
        if pool is not None:
            self._pool = pool
            self._owns_pool = False
            return
        if database_url is None:
            raise ValueError("database_url must be provided when pool is not supplied.")
        pool_class = self._load_pool_class()
        kwargs: dict[str, Any] = {
            "conninfo": database_url,
            "min_size": min_pool_size,
            "max_size": max_pool_size,
            "kwargs": {
                "autocommit": False,
                "connect_timeout": connect_timeout_seconds,
            },
            "check": pool_class.check_connection,
            "open": True,
        }
        self._pool = pool_class(**kwargs)
        self._owns_pool = True

    @property
    def storage_target(self) -> str:
        return "postgres"

    @property
    def pool(self) -> Any:
        return self._pool

    def ping(self) -> None:
        with self._pool.connection() as conn:
            # Verify both application tables exist so /readyz catches missing migrations.
            row = conn.execute(
                """
                select count(*) from information_schema.tables
                where table_schema = 'public'
                  and table_name in ('scenarios', 'scenario_outputs')
                """
            ).fetchone()
            found = int(row[0]) if row else 0
            if found < 2:
                raise RuntimeError(
                    "Database schema is incomplete: 'scenarios' and/or 'scenario_outputs' "
                    "tables are missing. Run the SQL migrations before serving traffic."
                )

    def close(self) -> None:
        if self._owns_pool:
            self._pool.close()

    def save(self, scenario: ScenarioRecord, output: ScenarioOutputRecord) -> ScenarioBundle:
        with self._pool.connection() as conn:
            with conn.transaction():
                persisted_scenario = self._upsert_scenario(conn, scenario)
                if persisted_scenario.id != scenario.id:
                    existing = self._fetch_bundle(conn, persisted_scenario.id)
                    if existing is None:
                        raise ValueError("Scenario idempotency conflict resolved without a persisted output.")
                    return existing

                self._insert_output(conn, output)
                created = self._fetch_bundle(conn, persisted_scenario.id)
                if created is None:
                    raise ValueError("Saved scenario could not be reloaded.")
                return created

    def get(self, scenario_id: str) -> ScenarioBundle | None:
        with self._pool.connection() as conn:
            return self._fetch_bundle(conn, scenario_id)

    def list_for_user(self, user_id: str, limit: int, cursor: str | None = None) -> ScenarioPage:
        with self._pool.connection() as conn:
            params: list[Any] = [user_id]
            cursor_clause = ""
            if cursor is not None:
                cursor_created_at, cursor_id = _decode_cursor(cursor)
                cursor_clause = " and (s.created_at, s.id) < (%s, %s)"
                params.extend([cursor_created_at, cursor_id])
            params.append(limit + 1)
            rows = conn.execute(
                """
                select
                    s.id,
                    s.user_id,
                    s.created_at,
                    s.inputs_snapshot,
                    s.assumptions_snapshot,
                    s.model_version,
                    s.idempotency_key,
                    s.module,
                    o.scenario_id,
                    o.computed_at,
                    o.output_blob
                from scenarios s
                join scenario_outputs o on o.scenario_id = s.id
                where s.user_id = %s
                """
                + cursor_clause
                + """
                order by s.created_at desc, s.id desc
                limit %s
                """,
                params,
            ).fetchall()
            bundles = tuple(self._row_to_bundle(row) for row in rows[:limit])
            next_cursor = None
            if len(rows) > limit and bundles:
                last = bundles[-1].scenario
                next_cursor = _encode_cursor(last.created_at, last.id)
            return ScenarioPage(items=bundles, next_cursor=next_cursor)

    def _upsert_scenario(self, conn: Any, scenario: ScenarioRecord) -> ScenarioRecord:
        market_region = str(scenario.inputs_snapshot.get("market_region", "national"))
        module = str(scenario.module)
        if scenario.idempotency_key is None:
            row = conn.execute(
                """
                insert into scenarios (
                    id,
                    user_id,
                    created_at,
                    module,
                    market_region,
                    inputs_snapshot,
                    assumptions_snapshot,
                    model_version,
                    idempotency_key
                )
                values (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                returning id, user_id, created_at, inputs_snapshot, assumptions_snapshot, model_version, idempotency_key
                """,
                [
                    scenario.id,
                    scenario.user_id,
                    scenario.created_at,
                    module,
                    market_region,
                    json.dumps(scenario.inputs_snapshot, sort_keys=True),
                    json.dumps(scenario.assumptions_snapshot, sort_keys=True),
                    scenario.model_version,
                    scenario.idempotency_key,
                ],
            ).fetchone()
            return self._row_to_scenario(row)

        row = conn.execute(
            """
            insert into scenarios (
                id,
                user_id,
                created_at,
                module,
                market_region,
                inputs_snapshot,
                assumptions_snapshot,
                model_version,
                idempotency_key
            )
            values (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            on conflict (user_id, idempotency_key) where idempotency_key is not null
            do update set idempotency_key = excluded.idempotency_key
            returning id, user_id, created_at, inputs_snapshot, assumptions_snapshot, model_version, idempotency_key
            """,
            [
                scenario.id,
                scenario.user_id,
                scenario.created_at,
                module,
                market_region,
                json.dumps(scenario.inputs_snapshot, sort_keys=True),
                json.dumps(scenario.assumptions_snapshot, sort_keys=True),
                scenario.model_version,
                scenario.idempotency_key,
            ],
        ).fetchone()
        return self._row_to_scenario(row)

    def _insert_output(self, conn: Any, output: ScenarioOutputRecord) -> None:
        probability, median_advantage, median_break_even = _output_summary_fields(output)
        conn.execute(
            """
            insert into scenario_outputs (
                scenario_id,
                computed_at,
                output_blob,
                probability_buy_beats_rent,
                median_terminal_advantage_cents,
                median_break_even_month
            )
            values (%s, %s, %s::jsonb, %s, %s, %s)
            on conflict (scenario_id) do nothing
            """,
            [
                output.scenario_id,
                output.computed_at,
                json.dumps(output.output_blob, sort_keys=True),
                probability,
                median_advantage,
                median_break_even,
            ],
        )

    def _fetch_bundle(self, conn: Any, scenario_id: str) -> ScenarioBundle | None:
        row = conn.execute(
            """
            select
                s.id,
                s.user_id,
                s.created_at,
                s.inputs_snapshot,
                s.assumptions_snapshot,
                s.model_version,
                s.idempotency_key,
                s.module,
                o.scenario_id,
                o.computed_at,
                o.output_blob
            from scenarios s
            join scenario_outputs o on o.scenario_id = s.id
            where s.id = %s
            """,
            [scenario_id],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_bundle(row)

    def _row_to_scenario(self, row: Any) -> ScenarioRecord:
        return ScenarioRecord(
            id=str(row[0]),
            user_id=str(row[1]),
            created_at=_normalize_timestamp(row[2]),
            inputs_snapshot=_normalize_json(row[3]),
            assumptions_snapshot=_normalize_json(row[4]),
            model_version=str(row[5]),
            idempotency_key=row[6],
            module=str(row[7]),
        )

    def _row_to_output(self, row: Any) -> ScenarioOutputRecord:
        return ScenarioOutputRecord(
            scenario_id=str(row[8]),
            computed_at=_normalize_timestamp(row[9]),
            output_blob=_normalize_json(row[10]),
        )

    def _row_to_bundle(self, row: Any) -> ScenarioBundle:
        return ScenarioBundle(
            scenario=self._row_to_scenario(row),
            output=self._row_to_output(row),
        )

    def _load_pool_class(self) -> Any:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "Postgres repository requires psycopg pool support. Install psycopg[binary,pool]."
            ) from exc
        return ConnectionPool
