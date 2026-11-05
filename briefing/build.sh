#!/bin/sh
# Refresh the briefing data and radar. Usage: build.sh [data|radar|all]
# Writes into /data/site; a failed fetch leaves the previous file in place.
SITE=/data/site
SCRIPTS=/opt/briefing/scripts
what="${1:-all}"
mkdir -p "$SITE"

if [ "$what" = "data" ] || [ "$what" = "all" ]; then
  for try in 1 2; do
    if python3 -I "$SCRIPTS/build_data.py" "$SITE/data.json.new" && [ -s "$SITE/data.json.new" ]; then
      mv "$SITE/data.json.new" "$SITE/data.json"
      echo "data.json updated"
      break
    fi
    echo "data build failed (try $try)"
    sleep 20
  done
  rm -f "$SITE/data.json.new"
fi

if [ "$what" = "radar" ] || [ "$what" = "all" ]; then
  if python3 -I "$SCRIPTS/fetch_radar.py" "$SITE/radar.gif.new"; then
    mv "$SITE/radar.gif.new" "$SITE/radar.gif"
    echo "radar.gif updated"
  else
    echo "radar fetch failed"
  fi
  rm -f "$SITE/radar.gif.new"
fi
