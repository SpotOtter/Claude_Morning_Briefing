#!/usr/bin/with-contenv bashio
# Starts the web server and the weekday refresh schedule.

TZNAME="$(bashio::config 'timezone')"
export TZ="${TZNAME:-America/Chicago}"
MAPS_KEY="$(bashio::config 'maps_key')"

SITE=/data/site
mkdir -p "$SITE"

# Always take the page from the add-on image; keep any data already fetched.
cp /opt/briefing/web/index.html "$SITE/index.html"
[ -f "$SITE/data.json" ] || cp /opt/briefing/web/data.json "$SITE/data.json"

# Settings the page can read. The Google Maps key is restricted to your domain in Google Cloud.
printf 'window.BRIEFING_CONFIG = %s;\n' "{\"mapsKey\": \"${MAPS_KEY}\"}" > "$SITE/config.js"

printf 'User-agent: *\nDisallow: /\n' > "$SITE/robots.txt"

cat > /etc/nginx/http.d/default.conf <<'EOF'
server {
    listen 80 default_server;
    root /data/site;
    index index.html;
    charset utf-8;
    # Keep search engines and crawlers out.
    add_header X-Robots-Tag "noindex, nofollow, noarchive, nosnippet" always;
    location / { try_files $uri $uri/ =404; }
    location ~* \.(json|gif|js)$ {
        add_header Cache-Control "no-cache";
        add_header X-Robots-Tag "noindex, nofollow, noarchive, nosnippet" always;
    }
}
EOF

# Every day, local time as set above: data at 4:30 AM and then on the hour, around
# the clock for the next-12-hours weather. Closures and crashes refresh on their own every
# 10 minutes, at times that never overlap the hourly data build.
cat > /etc/crontabs/root <<'EOF'
30 4 * * * /build.sh data
0 * * * * /build.sh data
5,15,25,35,45,55 * * * * /build.sh roads
EOF

bashio::log.info "Timezone ${TZ}. Fetching first data in the background."
/build.sh all &

crond -b -L /dev/stdout
bashio::log.info "Serving the briefing on port 80 (host port 8099)."
exec nginx -g 'daemon off;'
