"""Container entrypoint that safely URL-encodes Postgres credentials."""

import os
from sqlalchemy.engine import URL


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        url = URL.create(
            "postgresql+asyncpg",
            username=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
            host=os.environ.get("POSTGRES_HOST", "db"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            database=os.environ.get("POSTGRES_DB", "acgs_manager"),
        )
        os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)

    os.execvp(
        "uvicorn",
        ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"],
    )


if __name__ == "__main__":
    main()
