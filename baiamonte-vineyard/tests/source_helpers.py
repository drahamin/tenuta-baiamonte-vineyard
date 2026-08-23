from pathlib import Path


FRONTEND_SOURCES = (
    "app/static/app.js",
    "app/static/assets/analytics.js",
    "app/static/assets/lab-outlook.js",
    "app/static/assets/payroll.js",
    "app/static/assets/alerts.js",
    "app/static/assets/messaging.js",
    "app/static/assets/cellar.js",
    "app/static/assets/scouting.js",
    "app/static/assets/people.js",
    "app/static/assets/harvest.js",
    "app/static/assets/intake-review.js",
    "app/static/assets/system-docs.js",
    "app/static/assets/register.js",
)

BACKEND_SOURCES = (
    "app/main.py",
    "app/access.py",
    "app/sql_migrations.py",
    "app/domains/payroll.py",
    "app/domains/payroll_presence.py",
    "app/domains/attachments.py",
    "app/domains/payroll_admin_routes.py",
    "app/domains/worker_portal_routes.py",
    "app/domains/cellar_routes.py",
    "app/domains/dashboard_routes.py",
    "app/domains/alerts_intake_routes.py",
    "app/domains/public_routes.py",
    "app/domains/intelligence_routes.py",
    "app/domains/finance.py",
    "app/domains/messaging.py",
    "app/domains/whatsapp_people.py",
    "app/domains/cellar.py",
    "app/domains/alerts.py",
    "app/domains/harvest.py",
    "app/domains/harvest_routes.py",
    "app/domains/observation_routes.py",
    "app/domains/laboratory_routes.py",
    "app/domains/register.py",
    "app/domains/register_routes.py",
)


def frontend_source(root: Path) -> str:
    """Return the assembled classic-script frontend used by the browser."""
    return "\n".join((root / path).read_text(encoding="utf-8") for path in FRONTEND_SOURCES)


def backend_source(root: Path) -> str:
    """Return the staged backend while routes move out of the legacy module."""
    return "\n".join((root / path).read_text(encoding="utf-8") for path in BACKEND_SOURCES)
