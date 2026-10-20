#!/bin/sh
set -eu

mode=${1:-publish}
if [ "$mode" != publish ] && [ "$mode" != --dry-run ]; then
  echo "usage: scripts/publish_release_pair.sh [--dry-run]" >&2
  exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
working_repo=$(dirname "$script_dir")
key_id=baiamonte-secondary-owner-2026-1
release_key=${BAIAMONTE_RELEASE_KEY:-$HOME/.config/baiamonte-release/baiamonte-secondary-ed25519.pem}
remote=tenutabaiamonte-cpanel
remote_dir=cantinabaiamonte.com/private-releases/baiamonte-secondary
remote_base=apps/baiamonte-secondary
work=$(mktemp -d)
cleanup() { rm -rf "$work"; }
trap cleanup EXIT HUP INT TERM
chmod 700 "$work"

if [ "$mode" = publish ]; then
  test "$(git -C "$working_repo" branch --show-current)" = main || { echo "release publication requires main" >&2; exit 1; }
  test -z "$(git -C "$working_repo" status --porcelain --untracked-files=all)" || { echo "release publication requires a clean reviewed checkout" >&2; exit 1; }
  git -C "$working_repo" fetch --quiet origin main
  test "$(git -C "$working_repo" rev-parse HEAD)" = "$(git -C "$working_repo" rev-parse refs/remotes/origin/main)" || { echo "release publication requires the exact published main commit" >&2; exit 1; }
  source_commit=$(git -C "$working_repo" rev-parse HEAD)
  curl -fsS --max-time 20 -H 'Accept: application/vnd.github+json' -H 'User-Agent: Baiamonte-Release-Publisher/1' \
    "https://api.github.com/repos/drahamin/tenuta-baiamonte-vineyard/commits/$source_commit/check-runs" >"$work/check-runs.json"
  python3 - "$work/check-runs.json" <<'PY'
import json, pathlib, sys
runs=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")).get("check_runs", [])
release_checks=[item for item in runs if item.get("name") == "test"]
if not release_checks or any(item.get("status") != "completed" or item.get("conclusion") != "success" for item in release_checks):
    raise SystemExit("release publication requires a completed successful Release checks / test run")
print("github_release_checks=passed")
PY
  mkdir "$work/reviewed"
  git -C "$working_repo" archive --format=tar --output="$work/reviewed.tar" HEAD
  tar -xf "$work/reviewed.tar" -C "$work/reviewed"
  release_repo=$work/reviewed
  test -f "$release_key" || { echo "owner release key is unavailable" >&2; exit 1; }
  key_mode=$(stat -f %Lp "$release_key" 2>/dev/null || stat -c %a "$release_key")
  test "$key_mode" = 600 || { echo "owner release key must be mode 0600" >&2; exit 1; }
else
  echo "dry_run_notice=review gate intentionally skipped; signing uses an ephemeral fixture key"
  release_repo=$working_repo
  source_commit=$(git -C "$working_repo" rev-parse HEAD)
  release_key=$work/fixture-ed25519.pem
  openssl genpkey -algorithm Ed25519 -out "$release_key" >/dev/null 2>&1
  chmod 600 "$release_key"
  key_id=baiamonte-secondary-dry-run
fi

release_scripts=$release_repo/scripts
pair=$release_repo/release-pair.json
erp_source=$release_repo/baiamonte-secondary
python3 "$release_scripts/validate_release_pair.py" "$release_repo"
python3 "$release_scripts/audit_erp_publication.py" "$erp_source"
BAIAMONTE_SOURCE_COMMIT=$source_commit python3 "$release_scripts/test_erp_release.py"

values=$(python3 - "$pair" <<'PY'
import json, pathlib, sys
value=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["vineyard_version"], value["erp_version"], value["remote_contract"])
PY
)
set -- $values
vineyard_version=$1
erp_version=$2
contract=$3

python3 "$erp_source/ops/build_release_artifact.py" \
  --source "$erp_source" --output-dir "$work" --version "$erp_version" \
  --contract "$contract" --source-app-version "$vineyard_version" \
  --source-commit "$source_commit"
manifest=$work/baiamonte-secondary-$erp_version.manifest.json
envelope=$work/baiamonte-secondary-$erp_version.envelope.json
artifact=$work/baiamonte-secondary-$erp_version.tar.gz
"$erp_source/ops/sign_release_manifest.sh" "$manifest" "$release_key" "$key_id" "$envelope"

if [ "$mode" = --dry-run ]; then
  python3 - "$envelope" "$vineyard_version" "$erp_version" <<'PY'
import base64, json, pathlib, sys
envelope=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
payload=json.loads(base64.b64decode(envelope["payload_base64"], validate=True))
assert payload["source_app_version"] == sys.argv[2]
assert payload["version"] == sys.argv[3]
assert len(payload["source_commit"]) in (40, 64)
assert payload["schema_changes_required"] is False
assert all(item["automatic"] is False for item in payload["migrations"])
print("release_pair_dry_run_ok signed_fixture=true automatic_migrations=false")
PY
  exit 0
fi

artifact_name=$(basename "$artifact")
envelope_name=$(basename "$envelope")
if ssh "$remote" "test -e '$remote_dir/$artifact_name' -o -e '$remote_dir/$envelope_name'"; then
  echo "immutable release version already exists on the origin" >&2
  exit 1
fi
scp "$artifact" "$remote:$remote_dir/.$artifact_name.part"
scp "$envelope" "$remote:$remote_dir/.$envelope_name.part"
scp "$envelope" "$remote:$remote_dir/.latest.envelope.json.part"
ssh "$remote" "set -eu; test -d '$remote_dir'; test ! -e '$remote_dir/$artifact_name'; test ! -e '$remote_dir/$envelope_name'; chmod 0644 '$remote_dir/.$artifact_name.part' '$remote_dir/.$envelope_name.part' '$remote_dir/.latest.envelope.json.part'; mv '$remote_dir/.$artifact_name.part' '$remote_dir/$artifact_name'; mv '$remote_dir/.$envelope_name.part' '$remote_dir/$envelope_name'; mv '$remote_dir/.latest.envelope.json.part' '$remote_dir/latest.envelope.json'"
ssh "$remote" "/usr/local/bin/php '$remote_base/updater/automatic_release_installer.php' '$remote_base/config/config.php' --check-only"

attempt=0
while [ "$attempt" -lt 84 ]; do
  installed=$(ssh "$remote" "test -f '$remote_base/current/RELEASE_VERSION' && cat '$remote_base/current/RELEASE_VERSION' || true")
  if [ "$installed" = "$erp_version" ]; then
    ssh "$remote" "/usr/local/bin/php '$remote_base/current/ops/verify_authenticated_release.php' '$remote_base/config/config.php'"
    echo "release_pair_published vineyard=$vineyard_version erp=$erp_version"
    echo "next_step=perform the normal approved Vineyard Operations backup, install and health verification"
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 15
done
echo "website updater did not activate the paired ERP release within 21 minutes" >&2
exit 1
