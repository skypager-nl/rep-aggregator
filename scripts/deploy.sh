#!/bin/sh
# Build the frontend locally and push the app (add-on) to the HA Pi's local apps folder,
# then install it on first run or rebuild it afterwards. Uses the `ha-pi` SSH alias.
set -e
cd "$(dirname "$0")/.."
HOST=${HA_HOST:-ha-pi}
OUT=build/rep_aggregator

(cd web && npm run build)
rm -rf "$OUT" && mkdir -p "$OUT"
cp addon/rep_aggregator/* "$OUT"/
rsync -a --exclude .venv --exclude __pycache__ backend/ "$OUT/backend/"
cp -R web/dist "$OUT/web"
mkdir -p "$OUT/genuine" && cp data/photos/genuine/* "$OUT/genuine/" 2>/dev/null || true

# HA OS's SSH app has no rsync; stream a tarball instead.
ssh "$HOST" 'rm -rf /local_apps/rep_aggregator && mkdir -p /local_apps/rep_aggregator'
tar -C "$OUT" -czf - . | ssh "$HOST" 'tar -C /local_apps/rep_aggregator -xzf -'

ssh "$HOST" 'ha store reload >/dev/null
INFO=$(ha apps info local_rep_aggregator 2>/dev/null)
if echo "$INFO" | grep -q "^version: [0-9]"; then
  # version bumped in config.yaml -> update; same version -> rebuild
  if echo "$INFO" | grep -q "^update_available: true"; then
    ha apps update local_rep_aggregator
  else
    ha apps rebuild local_rep_aggregator
  fi
else
  ha apps install local_rep_aggregator && ha apps start local_rep_aggregator
fi
ha apps info local_rep_aggregator | grep -E "^(state|version|ingress_url):"' 
