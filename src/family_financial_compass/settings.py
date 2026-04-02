from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_ASSUMPTIONS_PATH, PROJECT_ROOT


def _strip_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        env_key = key.strip()
        if not env_key:
            continue
        os.environ.setdefault(env_key, _strip_env_value(raw_value))


def _parse_csv_env(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class AppSettings:
    host: str
    port: int
    scenario_store_backend: str
    data_dir: Path
    database_url: str | None
    database_min_pool_size: int
    database_max_pool_size: int
    database_connect_timeout_seconds: float
    assumptions_path: Path
    default_user_id: str
    scenario_list_default_limit: int
    scenario_list_max_limit: int
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "AppSettings":
        env_file = Path(os.getenv("FFC_ENV_FILE", str(PROJECT_ROOT / ".env")))
        _load_dotenv(env_file)
        database_url = os.getenv("FFC_DATABASE_URL")
        scenario_store_backend = os.getenv(
            "FFC_SCENARIO_STORE_BACKEND",
            "postgres" if database_url else "file",
        )
        return cls(
            host=os.getenv("FFC_HOST", "0.0.0.0"),
            port=int(os.getenv("FFC_PORT", "8000")),
            scenario_store_backend=scenario_store_backend,
            data_dir=Path(os.getenv("FFC_DATA_DIR", str(PROJECT_ROOT / "data"))),
            database_url=database_url,
            database_min_pool_size=int(os.getenv("FFC_DB_MIN_POOL_SIZE", "1")),
            database_max_pool_size=int(os.getenv("FFC_DB_MAX_POOL_SIZE", "10")),
            database_connect_timeout_seconds=float(os.getenv("FFC_DB_CONNECT_TIMEOUT_SECONDS", "5.0")),
            assumptions_path=Path(os.getenv("FFC_ASSUMPTIONS_PATH", str(DEFAULT_ASSUMPTIONS_PATH))),
            default_user_id=os.getenv("FFC_DEFAULT_USER_ID", "anonymous"),
            scenario_list_default_limit=int(os.getenv("FFC_SCENARIO_LIST_DEFAULT_LIMIT", "25")),
            scenario_list_max_limit=int(os.getenv("FFC_SCENARIO_LIST_MAX_LIMIT", "100")),
            allowed_origins=_parse_csv_env(os.getenv("FFC_ALLOWED_ORIGINS")),
        )
