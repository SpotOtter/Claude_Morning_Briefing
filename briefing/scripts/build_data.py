import json, gzip, re, math, sys, datetime as dt, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")
UA = "Mozilla/5.0 (mossy-head-briefing)"
LAT, LON = 30.77, -86.31
def get(url, h=None):
    r = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity", **(h or {})})
    b = urllib.request.urlopen(r, timeout=30).read()
    return gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b
def J(url): return json.loads(get(url, {"Accept": "application/geo+json"}))
def tryf(f, d):
    try: return f()
    except Exception as e: print("WARN", e, file=sys.stderr); return d

now = dt.datetime.now(CT)
day = now.date()
start = now.replace(minute=0, second=0, microsecond=0)   # the current hour
WINDOW = 12   # hours the page shows, starting from the hour it is opened

# ---- weather
pt = J(f"https://api.weather.gov/points/{LAT},{LON}")["properties"]
per = J(pt["forecastHourly"])["properties"]["periods"]
grid = J(pt["forecastGridData"])["properties"]
def gridvals(name):
    out = {}
    for v in grid.get(name, {}).get("values", []):
        t, d = v["validTime"].split("/")
        t0 = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
        m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?", d)
        n = int(m.group(1) or 0) * 24 + int(m.group(2) or 1)
        for i in range(n): out[(t0 + dt.timedelta(hours=i)).astimezone(CT).replace(minute=0, second=0, microsecond=0)] = v["value"]
    return out
gust = gridvals("windGust"); qpf = gridvals("quantitativePrecipitation"); hid = gridvals("heatIndex")
mph = lambda kmh: round(kmh * 0.621371) if kmh is not None else None
# Publish the next 36 hours with real timestamps. The page picks the 12 hours that
# start at the hour it is opened; the verdict and facts below cover the next 12 hours.
hours = []
for p in per:
    t = dt.datetime.fromisoformat(p["startTime"]).astimezone(CT)
    if t < start: continue
    if len(hours) >= 36: break
    sf = p["shortForecast"].lower()
    w = int(re.findall(r"\d+", p["windSpeed"])[-1])
    g = mph(gust.get(t)) or w
    hours.append({"ts": int(t.timestamp() * 1000), "h": f"{(t.hour-1)%12+1}{'a' if t.hour<12 else 'p'}", "temp": p["temperature"],
        "rain": (p["probabilityOfPrecipitation"] or {}).get("value") or 0, "wind": w, "gust": max(g, w),
        "fog": "fog" in sf or "haze" in sf and False, "storm": "thunder" in sf, "sky": p["shortForecast"]})
win = hours[:WINDOW]
temps = [h["temp"] for h in win]
high, low = max(temps), min(temps)
skies = [h["sky"] for h in win]
sky = (max(set(skies), key=skies.count) if skies else "See hourly")
rain_tot = sum(v for t, v in qpf.items() if start <= t < start + dt.timedelta(hours=WINDOW) and v) / 25.4
rain_pk = max([h["rain"] for h in win] or [0])
# sunrise/sunset (NOAA approx)
def sun(date, lat, lon, rise):
    n = date.timetuple().tm_yday
    lw = lon / 15; t = n + ((6 if rise else 18) - lw) / 24
    M = 0.9856 * t - 3.289
    L = (M + 1.916 * math.sin(math.radians(M)) + 0.02 * math.sin(math.radians(2 * M)) + 282.634) % 360
    RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L)))) % 360
    RA += (math.floor(L / 90) - math.floor(RA / 90)) * 90; RA /= 15
    sd = 0.39782 * math.sin(math.radians(L)); cd = math.cos(math.asin(sd))
    c = (math.cos(math.radians(90.833)) - sd * math.sin(math.radians(lat))) / (cd * math.cos(math.radians(lat)))
    H = (360 - math.degrees(math.acos(c))) / 15 if rise else math.degrees(math.acos(c)) / 15
    T = H + RA - 0.06571 * t - 6.622
    UT = (T - lw) % 24
    u = dt.datetime(date.year, date.month, date.day, tzinfo=dt.timezone.utc) + dt.timedelta(hours=UT)
    return u.astimezone(CT).strftime("%-I:%M %p")
sr, ss = sun(day, LAT, LON, True), sun(day, LAT, LON, False)
# past 48h rain from nearby stations
def obs_rain():
    for st in ["KCEW", "KDTS", "KPNS", "KECP"]:
        try:
            o = J(f"https://api.weather.gov/stations/{st}/observations?start={(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=48)).strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=200")["features"]
            tot = sum((f["properties"].get("precipitationLastHour") or {}).get("value") or 0 for f in o) / 25.4
            if o: return round(tot, 2), st
        except Exception as e: print("obs", st, e, file=sys.stderr)
    return None, None
r48, st = tryf(obs_rain, (None, None))
alerts = []
zones = ["FLZ008","FLZ009","FLZ010","FLC131","FLC091","FLC059","FLC133","FLC113"]
al = tryf(lambda: J("https://api.weather.gov/alerts/active?area=FL")["features"], [])
mine = [a for a in al if any(z.split("/")[-1] in zones for z in a["properties"]["affectedZones"]) or re.search(r"Walton|Okaloosa|Holmes|Washington|Santa Rosa", a["properties"].get("areaDesc", ""))]
for a in mine:
    p = a["properties"]; alerts.append({"level": "b" if p["severity"] in ("Severe", "Extreme") else "w", "text": p["event"]})
if not alerts: alerts = [{"level": "ok", "text": "No NWS watches or warnings for Walton, Okaloosa, Holmes, Washington or Santa Rosa"}]
storm_h = [h["h"] for h in win if h["storm"]]
fog_h = [h for h in win if h["fog"]]
mxg = max([h["gust"] for h in win] or [0]); mnw = min([h["wind"] for h in win] or [0]); mxw = max([h["wind"] for h in win] or [0])
if storm_h: lvl, lab, title = "watch", "Watch", f"Thunderstorms possible {storm_h[0]} to {storm_h[-1]}"
elif fog_h: lvl, lab, title = "watch", "Watch", "Fog early, drive slow"
elif rain_pk >= 50: lvl, lab, title = "watch", "Watch", f"Rain likely, up to {rain_pk}% chance"
elif mxg >= 25: lvl, lab, title = "watch", "Watch", f"Gusty, gusts to {mxg} mph"
else: lvl, lab, title = "clear", "Clear", "Good working weather"
if any(a["level"] != "ok" for a in alerts): lvl, lab = "stop" if any(a["level"] == "b" for a in alerts) else "watch", "Alert" if any(a["level"] == "b" for a in alerts) else "Watch"
tips = []
if fog_h: tips.append("Slow down early where fog sits on rural roads.")
if storm_h or rain_pk >= 50: tips.append("Expect wet job sites and slick dump areas. Lightning can pause loading, so haul the heavy loads before the storms.")
if mxg >= 25: tips.append(f"Gusts to {mxg} mph. Secure tarps and watch crosswinds on bridges and open stretches.")
if not tips: tips.append("Dry and workable. Good day to get loads moved.")
weather = {"sky": sky, "high": high, "low": low, "sunrise": sr, "sunset": ss, "sampleHours": False, "hours": hours,
  "facts": [
    {"k": "Rain, next 12 hrs", "v": f'{rain_tot:.2f}"' if rain_tot >= 0.01 else "Little to none", "note": f"Peak chance {rain_pk}%"},
    {"k": "Last 48 hours", "v": (f'{r48:.2f}"' if r48 is not None else None), "note": (f"Station {st}" if st else "Not available this run")},
    {"k": "Wind", "v": f"{mnw}–{mxw} mph", "note": f"Gusts to {mxg} mph"},
    {"k": "Heat index", "v": "Under 100°F" if high < 100 else f"Up to {high}°F", "note": "No heat concern" if high < 100 else "Heat risk, drink water"},
    {"k": "Sunrise", "v": sr, "note": ""}, {"k": "Sunset", "v": ss, "note": ""}],
  "alerts": alerts}

# ---- roads (FL511): see fl511.py. If FL511 cannot be read, keep the last good roads instead of saying all is clear.
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fl511
def previous_roads():
    try: return json.load(open(sys.argv[1].replace(".json.new", ".json")))["roads"]
    except Exception: return None
roads = fl511.roads() or fl511.stale_or_unavailable(previous_roads())
items = roads["items"]

# ---- news
def news():
    bad = re.compile(r"trump|biden|congress|senat|election|elect\b|democrat|republican|gop|vote|voter|ballot|mayor|governor|gov\.|proposition|campaign|candidate|shutdown|white house|politic|court|ukraine|gaza|israel|war\b|shoot|killed|dead|death|murder|isaias|hurricane|assault|abuse|arrest|police|prosecut|diddy|epstein", re.I)
    feeds = ["https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en" for q in
      ["Pensacola OR Crestview OR DeFuniak OR Okaloosa OR Walton County when:2d", "Florida Panhandle when:2d", "trucking OR diesel prices OR construction industry when:2d"]]
    feeds += [f"https://news.google.com/rss/headlines/section/topic/{t}?hl=en-US&gl=US&ceid=US:en" for t in ["BUSINESS", "SCIENCE", "SPORTS", "HEALTH", "TECHNOLOGY"]]
    pick = []; seen = set()
    for f in feeds:
        try: items = list(ET.fromstring(get(f)).iter("item"))
        except Exception as e: print("news", e, file=sys.stderr); continue
        got = 0
        for it in items:
            t = it.findtext("title") or ""
            if bad.search(t) or re.search(r"measures|ballot", t, re.I): continue
            try:
                from email.utils import parsedate_to_datetime
                if (dt.datetime.now(dt.timezone.utc) - parsedate_to_datetime(it.findtext("pubDate"))).days > 3: continue
            except Exception: continue
            title, _, src = t.rpartition(" - ")
            if src in seen or not title: continue
            seen.add(src); got += 1
            pick.append({"title": title, "text": "", "source": src, "url": it.findtext("link")})
            if got >= (2 if len(pick) < 4 else 1): break
        if len(pick) >= 5: break
    return pick[:5]
nw = tryf(news, [])

data = {"dayLabel": day.strftime("%A, %b %-d"), "place": "Mossy Head · Walton County, FL", "updated": now.strftime("%-I:%M %p CT"),
  "verdict": {"level": lvl, "label": lab, "title": title, "text": " ".join(tips)}, "weather": weather, "roads": roads, "news": nw,
  "sources": "Weather: National Weather Service, Tallahassee. Roads: FL511 (Florida only). Headlines: Google News."}
json.dump(data, open(sys.argv[1], "w"), indent=1)
print("ok", len(hours), len(items), len(nw), file=sys.stderr)
