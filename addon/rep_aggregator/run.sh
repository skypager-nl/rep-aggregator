#!/bin/sh
set -e
OPTS=/data/options.json

if [ ! -f /data/repagg.db ] && python -c "import json,sys; sys.exit(0 if json.load(open('$OPTS')).get('demo_data') else 1)"; then
  echo "[repagg] seeding demo data"
  repagg demo
fi

repagg seed-catalogue
repagg import-photos /app/genuine

# Report whether the RWI proxy route is safe (contacts an IP-echo service only, never RWI).
repagg egress-check || true

# One-shot demo purge (owner-requested): back up the database first, then purge.
if [ -f /share/rep_aggregator/purge-demo.request ]; then
  rm -f /share/rep_aggregator/purge-demo.request
  cp /data/repagg.db "/data/repagg.pre-purge-$(date +%Y%m%d-%H%M%S).db"
  repagg purge-demo > /share/rep_aggregator/purge-demo.result 2>&1 || true
fi

# One-shot, owner-approved RWI probe: runs only if the request file exists, then removes it.
PROBE=/share/rep_aggregator
if [ -f "$PROBE/probe.request" ]; then
  ONLY=$(tr -d ' \n' < "$PROBE/probe.request")
  rm -f "$PROBE/probe.request"
  repagg rwi-probe --out "$PROBE/probe-$(date +%Y%m%d-%H%M%S)" ${ONLY:+--only "$ONLY"} || true
fi

# Collectors stay off until explicitly enabled in the add-on options.
# RWI in particular must never run without the owner's go-ahead.
exec nice -n 10 repagg serve --host 0.0.0.0 --port 8099
