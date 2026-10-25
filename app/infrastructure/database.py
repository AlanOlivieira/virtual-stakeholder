from __future__ import annotations

import atexit
from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    required = ("PGHOST", "PGUSER", "PGPASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Faltam configurações do banco: " + ", ".join(missing))

    sslmode = os.getenv("PGSSLMODE", "require")
    if sslmode not in ("require", "verify-ca", "verify-full"):
        raise ValueError("Use PGSSLMODE=require ou verificação de certificado.")

    config = {
        "host": os.environ["PGHOST"],
        "port": os.getenv("PGPORT", "5432"),
        "user": os.environ["PGUSER"],
        "password": os.environ["PGPASSWORD"],
        "dbname": os.getenv("PGDATABASE", "postgres"),
        "sslmode": sslmode,
        "connect_timeout": "10",
        "application_name": "virtual-stakeholder",
    }
    if os.getenv("PGSSLROOTCERT"):
        config["sslrootcert"] = os.environ["PGSSLROOTCERT"]

    # Parâmetros separados evitam codificar caracteres especiais da senha em URL.
    pool = ConnectionPool(
        conninfo=make_conninfo(**config),
        min_size=1,
        max_size=int(os.getenv("DB_POOL_MAX_SIZE", "5")),
        timeout=10,
        open=False,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "prepare_threshold": None,
        },
    )
    try:
        pool.open(wait=True, timeout=15)
    except Exception:
        pool.close()
        raise
    atexit.register(pool.close)
    return pool
