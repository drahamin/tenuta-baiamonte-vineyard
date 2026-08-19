#!/usr/bin/env bash
set -euo pipefail

BAIAMONTE_HOST="${1:-baiamonte-ha}"

ssh "$BAIAMONTE_HOST" 'bash -s' <<'REMOTE_AUDIT'
set -euo pipefail

BAIAMONTE_BASE="http://172.30.33.6:8099"
BAIAMONTE_HEADERS=(-H "X-Ingress-Path: /api/hassio_ingress/release-audit" -H "X-Remote-User-Name: rahamin")
BAIAMONTE_TODAY="$(date +%F)"

for endpoint in dashboard grapes/dashboard cellar/dashboard agronomy/dashboard olives/dashboard finance/dashboard treatments/dashboard history/overview; do
  for year in 2020 2021 2022 2023 2024 2025 2026; do
    status=$(curl -sS -o /dev/null -w "%{http_code}" "${BAIAMONTE_HEADERS[@]}" "$BAIAMONTE_BASE/api/v1/$endpoint?year=$year")
    if [[ "$status" != "200" ]]; then
      printf 'FAIL endpoint=%s year=%s status=%s\n' "$endpoint" "$year" "$status"
      exit 1
    fi
  done
done

curl -sS "${BAIAMONTE_HEADERS[@]}" "$BAIAMONTE_BASE/api/v1/admin/control" | jq '{
  version:.runtime.version,
  database:.runtime.database,
  processing_errors_24h:.runtime.processing_errors_24h,
  unhealthy_processes:[.processes[]|select(.health!="healthy")|{code,health,last_error}],
  payment_integrity,
  data_quality
}'

curl -sS "${BAIAMONTE_HEADERS[@]}" "$BAIAMONTE_BASE/api/v1/system/status" | jq --arg today "$BAIAMONTE_TODAY" '{
  overall,
  planning:{
    calendar_connected:.planning.calendar_connected,
    tasks_connected:.planning.tasks_connected,
    duplicate_count:(.planning.duplicates|length),
    overdue_open:[.planning.work_items[]|select(.status!="done" and .status!="completed" and .status!="cancelled" and .due_date!=null and .due_date<$today)|{id,title,status,due_date}]
  }
}'

curl -sS "${BAIAMONTE_HEADERS[@]}" "$BAIAMONTE_BASE/api/v1/labs/history" | jq '{
  samples:length,
  missing_vintage:[.[]|select(.vintage_year==null)]|length,
  duplicate_ids:([.[].sample_id]|group_by(.)|map(select(length>1))|length),
  duplicate_codes:([.[].sample_code]|group_by(.)|map(select(length>1))|length),
  needs_review:[.[]|select(.needs_review==1)]|length
}'

curl -sS "${BAIAMONTE_HEADERS[@]}" "$BAIAMONTE_BASE/api/v1/treatments/dashboard?year=2026" | jq '{
  summary,
  duplicate_actions:([.actions[]|select(.kind=="record")|[(.entity_id//""),(.detail//""),(.status//"")]]|group_by(.)|map(select(length>1))|length)
}'

curl -sS "${BAIAMONTE_HEADERS[@]}" "$BAIAMONTE_BASE/api/v1/agronomy/dashboard?year=2026" | jq '{
  physical_tanks:(.cellar.tanks|length),
  duplicate_tank_ids:([.cellar.tanks[].id]|group_by(.)|map(select(length>1))|length),
  labels:(.tank_labels|length)
}'

curl -sS "${BAIAMONTE_HEADERS[@]}" "$BAIAMONTE_BASE/api/display-data" | jq '{
  display_year:.year,
  cellar_tanks:(.cellar.tanks|length),
  rain_72h_mm:(.pressure[0].input_snapshot|fromjson|.rain_72h_mm),
  rain_7d_mm:(.pressure[0].input_snapshot|fromjson|.rain_7d_mm),
  rainfall_source:(.pressure[0].input_snapshot|fromjson|.rainfall_source),
  next_treatment:.next_treatment_decision
}'

printf 'PASS all year-switch and integrity checks completed\n'
REMOTE_AUDIT
