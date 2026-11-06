#!/usr/bin/with-contenv bashio
# Starts the web server and the weekday refresh schedule.

TZNAME="$(bashio::config 'timezone')"
export TZ="${TZNAME:-America/Chicago}"
MAPS_KEY="$(bashio::config 'maps_key')"
export ADMIN_NAME="$(bashio::config 'admin_name')"
export ADMIN_TEMP="$(bashio::config 'admin_temp_password')"

SITE=/data/site
mkdir -p "$SITE"

# Always take the page from the add-on image; keep any data already fetched.
cp /opt/briefing/web/index.html "$SITE/index.html"
cp /opt/briefing/web/drivers.html "$SITE/drivers.html"
cp /opt/briefing/web/menu.js "$SITE/menu.js"
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
    location = /drivers { try_files /drivers.html =404; }
    location /api/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
        proxy_set_header CF-Connecting-IP $http_cf_connecting_ip;
        proxy_set_header CF-Visitor $http_cf_visitor;
        add_header Cache-Control "no-store" always;
        add_header X-Robots-Tag "noindex, nofollow, noarchive, nosnippet" always;
    }
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

python3 -I /opt/briefing/scripts/dispatch_server.py &
crond -b -L /dev/stdout
bashio::log.info "Serving the briefing on port 80 (host port 8099)."
exec nginx -g 'daemon off;'
