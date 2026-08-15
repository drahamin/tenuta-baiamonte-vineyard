"""Guarded patcher for the built-in Home Assistant authorization page."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
from pathlib import Path
import re


START = "<!-- TENUTA BAIAMONTE LOGIN V2 START -->"
END = "<!-- TENUTA BAIAMONTE LOGIN V2 END -->"
CACHE_META = (
    '<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">'
    '<meta http-equiv="Pragma" content="no-cache">'
    '<meta http-equiv="Expires" content="0">'
)

STYLE = f"""{START}
<style id="tenuta-baiamonte-login-v2">
  :root {{ color-scheme: dark; background: #11110f !important; }}
  body {{
    min-height: 100%;
    padding: max(22px, var(--safe-area-inset-top)) 0 max(22px, var(--safe-area-inset-bottom)) !important;
    background:
      radial-gradient(circle at 50% -10%, rgba(143,35,56,.40), transparent 42%),
      radial-gradient(circle at 8% 94%, rgba(202,162,74,.10), transparent 34%),
      linear-gradient(145deg, #181814 0%, #0b0b0a 60%, #15110f 100%);
    color: #f7f2e8;
  }}
  .content {{ max-width: 400px !important; position: relative; z-index: 1; }}
  .header.baiamonte-header {{
    flex-direction: column;
    gap: 10px;
    margin-bottom: 22px;
    padding-top: 0;
    text-align: center;
  }}
  .header.baiamonte-header img {{
    display: block;
    width: min(250px, 72vw) !important;
    height: auto !important;
    filter: drop-shadow(0 10px 24px rgba(0,0,0,.42));
  }}
  .baiamonte-wordmark-fallback {{
    font-size: clamp(25px, 8vw, 36px);
    font-weight: 300;
    letter-spacing: .19em;
  }}
  .baiamonte-kicker {{
    color: rgba(247,242,232,.64);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: .28em;
    text-transform: uppercase;
  }}
  .baiamonte-login-card {{
    overflow: hidden;
    border: 1px solid rgba(202,162,74,.42);
    border-radius: 16px;
    background: #191815;
    box-shadow: 0 22px 65px rgba(0,0,0,.42);
  }}
  .baiamonte-login-card ha-authorize {{
    color-scheme: dark;
    color: #f7f2e8;
    display: block;
    --primary-color: #9f2941;
    --accent-color: #caa24a;
    --primary-text-color: #f7f2e8;
    --secondary-text-color: #c4bbad;
    --link-text-color: #d8b45e;
    --disabled-text-color: #766f65;
    --primary-background-color: #191815;
    --secondary-background-color: #211f1b;
    --card-background-color: #191815;
    --divider-color: rgba(202,162,74,.24);
    --mdc-theme-primary: #b83450;
    --mdc-theme-on-primary: #fffaf0;
    --mdc-text-field-fill-color: rgba(255,255,255,.055);
    --mdc-text-field-ink-color: #f7f2e8;
    --mdc-text-field-label-ink-color: #c4bbad;
    --mdc-text-field-idle-line-color: rgba(202,162,74,.48);
    --mdc-text-field-hover-line-color: #caa24a;
    --input-fill-color: rgba(255,255,255,.055);
    --input-ink-color: #f7f2e8;
    --input-label-ink-color: #c4bbad;
    --wa-color-brand-fill-loud: #9f2941;
    --wa-color-brand-on-loud: #fffaf0;
    --wa-color-focus: #caa24a;
  }}
  .baiamonte-security-note {{
    margin: 16px 0 0;
    color: rgba(247,242,232,.58);
    font-size: 11px;
    letter-spacing: .08em;
    text-align: center;
    text-transform: uppercase;
  }}
  [hidden] {{ display: none !important; }}
  @media (max-width: 480px) {{
    body {{ padding-left: 0 !important; padding-right: 0 !important; }}
    .content {{ padding: 0 16px !important; }}
  }}
</style>
{END}"""

HEADER = f"""{START}
<div class="header baiamonte-header">
  <img src="/local/baiamonte-branding/logon-logo.png" alt="Tenuta Baiamonte" onerror="this.hidden=true;this.nextElementSibling.hidden=false">
  <span class="baiamonte-wordmark-fallback" hidden>BAIAMONTE</span>
  <div class="baiamonte-kicker">Estate Operations · Sicilia</div>
</div>
{END}"""

FORM = f"""{START}
<section class="baiamonte-login-card"><ha-authorize></ha-authorize></section>
<div class="baiamonte-security-note">Secure estate access</div>
{END}"""


class BrandingError(RuntimeError):
    """Raised when a safe, exact patch cannot be made."""


@dataclass(frozen=True)
class BrandingResult:
    """Describe an apply result."""

    path: Path
    changed: bool


def _frontend_page(frontend_root: Path) -> Path:
    page = frontend_root / "authorize.html"
    if not page.is_file():
        raise BrandingError(f"Home Assistant authorize.html is missing from {frontend_root}")
    return page


def _root() -> Path:
    module = importlib.import_module("hass_frontend")
    return Path(module.__file__).resolve().parent


def render(original: str) -> str:
    """Create the approved layout without editing the authorization component."""
    if START in original:
        if CACHE_META in original:
            return original
        if "</head>" not in original:
            raise BrandingError("the Home Assistant login page has no closing head element")
        return original.replace("</head>", f"{CACHE_META}</head>", 1)
    branded, title_count = re.subn(
        r"<title>[^<]*</title>", "<title>Tenuta Baiamonte</title>", original, count=1
    )
    branded, icon_count = re.subn(
        r'<link rel="icon" href="[^"]+">',
        '<link rel="icon" type="image/png" href="/local/baiamonte-branding/favicon.png">',
        branded,
        count=1,
    )
    branded, header_count = re.subn(
        r'<div class="header"><img\s+src="[^"]+"\s+alt="[^"]*"></div>',
        HEADER,
        branded,
        count=1,
    )
    branded, form_count = re.subn(
        r"<ha-authorize></ha-authorize>", FORM, branded, count=1
    )
    if (title_count, icon_count, header_count, form_count) != (1, 1, 1, 1):
        raise BrandingError(
            "the Home Assistant login layout changed; stock was preserved "
            f"(title={title_count}, icon={icon_count}, header={header_count}, form={form_count})"
        )
    if "</head>" not in branded:
        raise BrandingError("the Home Assistant login page has no closing head element")
    return branded.replace("</head>", f"{CACHE_META}{STYLE}</head>", 1)


def apply_branding(config_dir: Path, frontend_root: Path | None = None) -> BrandingResult:
    """Back up stock and atomically publish the approved page."""
    frontend_root = frontend_root or _root()
    page = _frontend_page(frontend_root)
    logo = config_dir / "www" / "baiamonte-branding" / "logon-logo.png"
    favicon = config_dir / "www" / "baiamonte-branding" / "favicon.png"
    if not logo.is_file() or not favicon.is_file():
        raise BrandingError("the tested Baiamonte login assets are unavailable")
    original = page.read_text(encoding="utf-8")
    branded = render(original)
    if branded == original:
        return BrandingResult(page, False)
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:16]
    backups = config_dir / ".baiamonte-branding-backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"authorize-{digest}.html"
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
    temporary = page.with_suffix(".html.baiamonte-v2")
    temporary.write_text(branded, encoding="utf-8")
    temporary.replace(page)
    return BrandingResult(page, True)


def restore_vendor_page(config_dir: Path, frontend_root: Path | None = None) -> Path:
    """Atomically restore the newest verified stock page."""
    frontend_root = frontend_root or _root()
    page = _frontend_page(frontend_root)
    backups = config_dir / ".baiamonte-branding-backups"
    candidates = sorted(
        backups.glob("authorize-*.html"), key=lambda item: item.stat().st_mtime, reverse=True
    )
    stock = next(
        (candidate for candidate in candidates if START not in candidate.read_text(encoding="utf-8")),
        None,
    )
    if stock is None:
        raise BrandingError(f"no verified stock login backup exists in {backups}")
    temporary = page.with_suffix(".html.baiamonte-restore")
    temporary.write_text(stock.read_text(encoding="utf-8"), encoding="utf-8")
    temporary.replace(page)
    return page
