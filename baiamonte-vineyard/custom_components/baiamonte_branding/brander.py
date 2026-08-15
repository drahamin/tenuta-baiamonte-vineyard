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
FRESH_LOGIN_NAME = "baiamonte-login-20260815-v1.html"
LATEST_ENTRY_NAME = "baiamonte-core-latest-20260815-v1.js"
LEGACY_ENTRY_NAME = "baiamonte-core-legacy-20260815-v1.js"

STYLE = f"""{START}
<style id="tenuta-baiamonte-login-v2">
  :root {{
    color-scheme: dark;
    background: #0b0b09 !important;
    --primary-color: #8f2338;
    --accent-color: #d2ad4f;
    --ha-color-primary-40: #a82d47;
    --ha-color-primary-50: #8f2338;
    --ha-color-primary-60: #741b2c;
  }}
  body {{
    min-height: 100%;
    padding: max(22px, var(--safe-area-inset-top)) 0 max(22px, var(--safe-area-inset-bottom)) !important;
    background:
      radial-gradient(circle at 50% -12%, rgba(143,35,56,.38), transparent 40%),
      radial-gradient(circle at 7% 92%, rgba(210,173,79,.12), transparent 35%),
      linear-gradient(145deg, #181612 0%, #090908 58%, #15100e 100%);
    color: #f7f2e8;
  }}
  body::before {{
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: .24;
    background-image:
      linear-gradient(30deg, transparent 49.5%, rgba(210,173,79,.08) 50%, transparent 50.5%),
      linear-gradient(150deg, transparent 49.5%, rgba(143,35,56,.08) 50%, transparent 50.5%);
    background-size: 58px 58px;
    mask-image: linear-gradient(to bottom, rgba(0,0,0,.8), transparent 82%);
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
    width: min(238px, 68vw) !important;
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
    border: 1px solid rgba(210,173,79,.48);
    border-radius: 20px;
    background: linear-gradient(155deg, rgba(31,28,22,.98), rgba(19,18,15,.99));
    box-shadow: 0 26px 72px rgba(0,0,0,.48), inset 0 1px rgba(255,255,255,.035);
  }}
  .baiamonte-login-card ha-authorize {{
    color-scheme: dark;
    color: #f7f2e8;
    display: block;
    --primary-color: #a82d47;
    --accent-color: #d2ad4f;
    --primary-text-color: #f7f2e8;
    --secondary-text-color: #c4bbad;
    --link-text-color: #e0be68;
    --disabled-text-color: #766f65;
    --primary-background-color: #191815;
    --secondary-background-color: #211f1b;
    --card-background-color: #191815;
    --divider-color: rgba(210,173,79,.24);
    --outline-color: rgba(210,173,79,.38);
    --ha-card-background: transparent;
    --ha-card-border-color: transparent;
    --ha-card-border-width: 0;
    --ha-card-box-shadow: none;
    --ha-card-border-radius: 18px;
    --mdc-theme-primary: #b93651;
    --mdc-theme-on-primary: #fffaf0;
    --mdc-text-field-fill-color: rgba(255,255,255,.055);
    --mdc-text-field-ink-color: #f7f2e8;
    --mdc-text-field-label-ink-color: #c4bbad;
    --mdc-text-field-idle-line-color: rgba(202,162,74,.48);
    --mdc-text-field-hover-line-color: #caa24a;
    --input-fill-color: rgba(255,255,255,.055);
    --input-ink-color: #f7f2e8;
    --input-label-ink-color: #c4bbad;
    --wa-color-brand-fill-loud: #a82d47;
    --wa-color-brand-on-loud: #fffaf0;
    --wa-color-focus: #d2ad4f;
    --ha-button-primary-color: #a82d47;
    --ha-button-primary-text-color: #fffaf0;
  }}
  .baiamonte-login-card ha-authorize .card-content {{
    border: 0 !important;
    border-radius: 20px !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 26px 24px 20px !important;
  }}
  .baiamonte-login-card ha-authorize h1 {{
    margin: 0 0 22px !important;
    color: #fffaf0 !important;
    font-family: Georgia, "Times New Roman", serif !important;
    font-size: clamp(30px, 8vw, 42px) !important;
    font-weight: 400 !important;
    letter-spacing: -.025em !important;
    text-align: center;
  }}
  .baiamonte-login-card ha-authorize .footer {{
    border-top: 1px solid rgba(210,173,79,.18);
    padding: 12px 18px 14px !important;
  }}
  .baiamonte-login-card input,
  .baiamonte-login-card ha-textfield {{
    --mdc-text-field-fill-color: rgba(255,255,255,.06);
    --mdc-text-field-idle-line-color: rgba(210,173,79,.42);
    --mdc-text-field-hover-line-color: #d2ad4f;
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
    .baiamonte-login-card ha-authorize .card-content {{ padding: 22px 18px 16px !important; }}
  }}
</style>
{END}"""

HEADER = f"""{START}
<div class="header baiamonte-header">
  <img src="/local/baiamonte-branding/logon-logo.png?v=20260815-1" alt="Tenuta Baiamonte" onerror="this.hidden=true;this.nextElementSibling.hidden=false">
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
        updated, style_count = re.subn(
            re.escape(START)
            + r'\s*<style id="tenuta-baiamonte-login-v2">.*?</style>\s*'
            + re.escape(END),
            STYLE,
            original,
            count=1,
            flags=re.DOTALL,
        )
        if style_count != 1:
            raise BrandingError("the existing Baiamonte login style could not be upgraded safely")
        updated = updated.replace(
            '/local/baiamonte-branding/logon-logo.png"',
            '/local/baiamonte-branding/logon-logo.png?v=20260815-1"',
        ).replace(
            '<link rel="icon" type="image/png" href="/local/baiamonte-branding/favicon.png">',
            '<link rel="icon" type="image/png" href="/local/baiamonte-branding/favicon.png?v=20260815-1">',
        )
        if CACHE_META in updated:
            return updated
        if "</head>" not in updated:
            raise BrandingError("the Home Assistant login page has no closing head element")
        return updated.replace("</head>", f"{CACHE_META}</head>", 1)
    branded, title_count = re.subn(
        r"<title>[^<]*</title>", "<title>Tenuta Baiamonte</title>", original, count=1
    )
    branded, icon_count = re.subn(
        r'<link rel="icon" href="[^"]+">',
        '<link rel="icon" type="image/png" href="/local/baiamonte-branding/favicon.png?v=20260815-1">',
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


def _patch_entry_flow(config_dir: Path, frontend_root: Path) -> bool:
    """Send Home Assistant's regular login handoff to a fresh branded page."""
    index = frontend_root / "index.html"
    if not index.is_file():
        raise BrandingError(f"Home Assistant index.html is missing from {frontend_root}")
    index_text = index.read_text(encoding="utf-8")
    match = re.search(r"/frontend_latest/(core\.[a-f0-9]+\.js)", index_text)
    if match is not None:
        core_name = match.group(1)
    else:
        candidates = sorted((frontend_root / "frontend_latest").glob("core.*.js"))
        if len(candidates) != 1:
            raise BrandingError("the current Home Assistant core frontend bundle was not found")
        core_name = candidates[0].name
    core = frontend_root / "frontend_latest" / core_name
    if not core.is_file():
        raise BrandingError(f"the Home Assistant core frontend bundle is missing: {core}")

    stock_handoff = "/auth/authorize?response_type=code"
    branded_handoff = f"/local/{FRESH_LOGIN_NAME}?response_type=code"
    previous_handoff = r"/local/baiamonte-login-[a-zA-Z0-9-]+\.html\?response_type=code"
    backups = config_dir / ".baiamonte-branding-backups"
    backups.mkdir(parents=True, exist_ok=True)

    def patch_bundle(bundle: Path, published_name: str, suffix: str) -> bool:
        bundle_text = bundle.read_text(encoding="utf-8")
        changed = False
        if branded_handoff not in bundle_text:
            if bundle_text.count(stock_handoff) == 1:
                patched = bundle_text.replace(stock_handoff, branded_handoff, 1)
            elif len(re.findall(previous_handoff, bundle_text)) == 1:
                patched = re.sub(previous_handoff, branded_handoff, bundle_text, count=1)
            else:
                raise BrandingError(f"the {suffix} authorization handoff changed; bundle was preserved")
            digest = hashlib.sha256(bundle_text.encode("utf-8")).hexdigest()[:16]
            backup = backups / f"{bundle.name}-{digest}.js"
            if not backup.exists():
                backup.write_text(bundle_text, encoding="utf-8")
            temporary = bundle.with_suffix(f".js.baiamonte-{suffix}")
            temporary.write_text(patched, encoding="utf-8")
            temporary.replace(bundle)
            bundle_text = patched
            changed = True
        published = config_dir / "www" / published_name
        if bundle_text.count(branded_handoff) != 1:
            raise BrandingError(f"the published {suffix} Baiamonte entry bundle was not patched")
        if not published.exists() or published.read_text(encoding="utf-8") != bundle_text:
            temporary = published.with_suffix(".js.tmp")
            temporary.write_text(bundle_text, encoding="utf-8")
            temporary.replace(published)
            changed = True
        return changed

    modern_changed = patch_bundle(core, LATEST_ENTRY_NAME, "modern")
    core_url = f"/frontend_latest/{core_name}"
    versioned_core_url = f"/local/{LATEST_ENTRY_NAME}"
    index_changed = False
    if versioned_core_url not in index_text:
        occurrences = index_text.count(core_url)
        if occurrences != 2:
            raise BrandingError(
                "the frontend core bundle references changed; index was preserved "
                f"(references={occurrences})"
            )
        digest = hashlib.sha256(index_text.encode("utf-8")).hexdigest()[:16]
        backup = backups / f"index-{digest}.html"
        if not backup.exists():
            backup.write_text(index_text, encoding="utf-8")
        index_text = re.sub(re.escape(core_url) + r"(?:\?[^\"']+)?", versioned_core_url, index_text)
        temporary = index.with_suffix(".html.baiamonte-entry")
        temporary.write_text(index_text, encoding="utf-8")
        temporary.replace(index)
        index_changed = True

    legacy_match = re.search(r"/frontend_es5/(core\.[a-f0-9]+\.js)", index_text)
    if legacy_match is not None:
        legacy_name = legacy_match.group(1)
    else:
        candidates = sorted((frontend_root / "frontend_es5").glob("core.*.js"))
        if len(candidates) != 1:
            raise BrandingError("the legacy Home Assistant core frontend bundle was not found")
        legacy_name = candidates[0].name
    legacy_core = frontend_root / "frontend_es5" / legacy_name
    if not legacy_core.is_file():
        raise BrandingError(f"the legacy Home Assistant core frontend bundle is missing: {legacy_core}")
    legacy_changed = patch_bundle(legacy_core, LEGACY_ENTRY_NAME, "legacy")
    legacy_url = f"/frontend_es5/{legacy_name}"
    versioned_legacy_url = f"/local/{LEGACY_ENTRY_NAME}"
    legacy_index_changed = False
    if versioned_legacy_url not in index_text:
        occurrences = index_text.count(legacy_url)
        if occurrences != 1:
            raise BrandingError(
                "the legacy core bundle references changed; index was preserved "
                f"(references={occurrences})"
            )
        current_index = index.read_text(encoding="utf-8")
        current_index = re.sub(
            re.escape(legacy_url) + r"(?:\?[^\"']+)?", versioned_legacy_url, current_index
        )
        temporary = index.with_suffix(".html.baiamonte-entry")
        temporary.write_text(current_index, encoding="utf-8")
        temporary.replace(index)
        legacy_index_changed = True
    return modern_changed or index_changed or legacy_changed or legacy_index_changed


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
    fresh_login = config_dir / "www" / FRESH_LOGIN_NAME
    if not fresh_login.exists() or fresh_login.read_text(encoding="utf-8") != branded:
        fresh_temporary = fresh_login.with_suffix(".html.tmp")
        fresh_temporary.write_text(branded, encoding="utf-8")
        fresh_temporary.replace(fresh_login)
    entry_changed = _patch_entry_flow(config_dir, frontend_root)
    if branded == original:
        return BrandingResult(page, entry_changed)
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
