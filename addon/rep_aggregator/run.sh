#!/bin/sh
set -e
OPTS=/data/options.json

if [ ! -f /data/repagg.db ] && python -c "import json,sys; sys.exit(0 if json.load(open('$OPTS')).get('demo_data') else 1)"; then
  echo "[repagg] seeding demo data"
  repagg demo
fi

repagg import-photos /app/genuine

# Collectors stay off until explicitly enabled in the add-on options.
# RWI in particular must never run without the owner's go-ahead.
exec nice -n 10 repagg serve --host 0.0.0.0 --port 8099
