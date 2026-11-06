#!/bin/sh
# Refresh the briefing data. Usage: build.sh [data|roads|all]
# "roads" refreshes only the closures and crashes in the existing data.json.
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

if [ "$what" = "roads" ] && [ -s "$SITE/data.json" ]; then
  if python3 -I "$SCRIPTS/build_roads.py" "$SITE/data.json"; then
    echo "roads updated"
  else
    echo "roads refresh failed; keeping the previous file"
  fi
  rm -f "$SITE/data.json.new"
fi
