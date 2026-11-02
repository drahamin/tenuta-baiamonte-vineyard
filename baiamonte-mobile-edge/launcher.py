"""Candidate runtime: no host ports, API privilege, or automatic activation."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    options = json.loads(Path("/data/options.json").read_text())
    if options.get("enabled") is not True:
        print("Mobile edge is disabled.", flush=True)
        return 0
    token = options.get("tunnel_token", "")
    assets_file = Path("/data/login-assets.json")
    if not isinstance(token, str) or not 64 <= len(token) <= 4096 or not assets_file.is_file():
        print("Mobile edge is not ready; no connector started.", flush=True)
        return 1
    from gateway import validate_assets
    assets = json.loads(assets_file.read_text())
    validate_assets(assets)
    if not assets:
        print("Frozen login assets are missing; no connector started.", flush=True)
        return 1
    token_path = Path("/data/.tunnel-token")
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
