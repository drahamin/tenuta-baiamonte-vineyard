#!/bin/sh
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: sign_release_manifest.sh MANIFEST PRIVATE_KEY KEY_ID ENVELOPE" >&2
  exit 2
fi
manifest=$1
private_key=$2
key_id=$3
envelope=$4
case "$key_id" in
  *[!A-Za-z0-9._-]*|'') echo "invalid key id" >&2; exit 2 ;;
esac
payload_file=$(mktemp)
signature_file=$(mktemp)
cleanup() { rm -f "$payload_file" "$signature_file"; }
trap cleanup EXIT HUP INT TERM
chmod 600 "$payload_file" "$signature_file"
python3 - "$manifest" "$payload_file" <<'PY'
import json, pathlib, sys
value=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
pathlib.Path(sys.argv[2]).write_bytes(json.dumps(value,sort_keys=True,separators=(",",":")).encode())
PY
openssl pkeyutl -sign -rawin -inkey "$private_key" -in "$payload_file" -out "$signature_file"
python3 - "$payload_file" "$signature_file" "$key_id" "$envelope" <<'PY'
import base64, json, pathlib, sys
payload=pathlib.Path(sys.argv[1]).read_bytes()
signature=pathlib.Path(sys.argv[2]).read_bytes()
envelope={
  "schema":1,
  "payload_base64":base64.b64encode(payload).decode(),
  "signature":{"algorithm":"Ed25519","key_id":sys.argv[3],"value_base64":base64.b64encode(signature).decode()},
}
pathlib.Path(sys.argv[4]).write_text(json.dumps(envelope,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
PY
echo "signed_manifest=$envelope key_id=$key_id"
