from pathlib import Path


FRONTEND_SOURCES = (
    "app/static/app.js",
    "app/static/assets/payroll.js",
    "app/static/assets/alerts.js",
    "app/static/assets/messaging.js",
    "app/static/assets/cellar.js",
    "app/static/assets/scouting.js",
    "app/static/assets/people.js",
    "app/static/assets/harvest.js",
)

BACKEND_SOURCES = (
    "app/main.py",
    "app/access.py",
    "app/sql_migrations.py",
    "app/domains/payroll.py",
    "app/domains/finance.py",
    "app/domains/messaging.py",
    "app/domains/cellar.py",
    "app/domains/alerts.py",
    "app/domains/harvest.py",
)


def frontend_source(root: Path) -> str:
    """Return the assembled classic-script frontend used by the browser."""
    return "\n".join((root / path).read_text(encoding="utf-8") for path in FRONTEND_SOURCES)


def backend_source(root: Path) -> str:
    """Return the staged backend while routes move out of the legacy module."""
    return "\n".join((root / path).read_text(encoding="utf-8") for path in BACKEND_SOURCES)
