"""Candidate runtime: no host ports, API privilege, or automatic activation."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def prepare_login_assets(options, data_dir):
    """Materialize only a validated, explicitly supplied frozen path list."""
    from gateway import validate_assets
    assets = options.get("login_assets")
    if not isinstance(assets, list) or not 1 <= len(assets) <= 512:
        raise ValueError("missing or invalid frozen asset list")
    if any(not isinstance(path, str) or len(path) > 256 for path in assets):
        raise ValueError("invalid frozen asset path")
    validate_assets(assets)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=data_dir,
                                         prefix=".login-assets-", delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            # Keep only supplied paths: validate_assets adds its fixed branding
            # paths at runtime, and /local is not an operator-configurable prefix.
            json.dump(sorted(set(assets)), stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(data_dir / "login-assets.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(data_dir=Path("/data")):
    options = json.loads((data_dir / "options.json").read_text())
    if options.get("enabled") is not True:
        print("Mobile edge is disabled.", flush=True)
        return 0
    token = options.get("tunnel_token", "")
    if not isinstance(token, str) or not 64 <= len(token) <= 4096:
        print("Mobile edge is not ready; no connector started.", flush=True)
        return 1
    try:
        prepare_login_assets(options, data_dir)
    except (ValueError, TypeError, OSError):
        print("Frozen login assets are missing or invalid; no connector started.", flush=True)
        return 1
    token_path = data_dir / ".tunnel-token"
    fd = os.open(token_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(token)
    gateway = subprocess.Popen([sys.executable, "gateway.py"])
    connector = None
    try:
        import socket
        for _ in range(50):
            if gateway.poll() is not None:
                return 1
            try:
                with socket.create_connection(("127.0.0.1", 8184), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            return 1
        connector = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "run", "--token-file", str(token_path)])
        def stop(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while gateway.poll() is None and connector.poll() is None:
            time.sleep(0.2)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in (connector, gateway):
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        token_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
