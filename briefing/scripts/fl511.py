"""FL511 closures and crashes for the briefing. Used by build_data.py (full build) and build_roads.py (frequent refresh)."""
import json, gzip, re, math, sys, datetime as dt, urllib.request, urllib.parse
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")   # FL511 prints its times in Eastern
UA = "Mozilla/5.0 (mossy-head-briefing)"
LAT, LON = 30.77, -86.31
LINKS = [{"label": "FL511 map", "url": "https://fl511.com"}, {"label": "Alabama 511", "url": "https://algotraffic.com"}]

def fget(url):
    r = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    b = urllib.request.urlopen(r, timeout=30).read()
    return gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b

def fetch_raw():
    def layer(name):
        q = {"columns":[{"data":None,"name":""}],"order":[{"column":0,"dir":"asc"}],"start":0,"length":300,"search":{"value":""}}
        return json.loads(fget("https://fl511.com/List/GetData/%s?query=%s&lang=en" % (name, urllib.parse.quote(json.dumps(q)))))
    def icons(name):
        d = json.loads(fget("https://fl511.com/map/mapIcons/" + name))
        return {str(i["itemId"]): i["location"] for i in d["item2"]}
    out = {}
    for name in ["Incidents", "Closures", "Construction"]:
        d = layer(name); ic = icons(name)
        out[name] = [{k: r.get(k) for k in ["id","roadwayName","description","isFullClosure","detourDescription","county","endDate"]} | {"lat": (ic.get(str(r["id"])) or [None,None])[0], "lon": (ic.get(str(r["id"])) or [None,None])[1]} for r in d["data"]]
    return out

def ended(r, now):
    """True if FL511 gives an end time that has already passed (the event is over)."""
    s = r.get("endDate")
    if not s: return False
    try: return dt.datetime.strptime(s, "%m/%d/%y, %I:%M %p").replace(tzinfo=ET) <= now
    except Exception: return False

def pan(r): return r.get("lat") and 29.9 <= r["lat"] <= 31.6 and -87.8 <= r["lon"] <= -84.8
clean = lambda s: re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()
dist = lambda r: math.hypot((r['lon']-LON)*math.cos(math.radians(LAT))*69, (r['lat']-LAT)*69)

def build(raw, now):
    items = []
    for r in raw.get("Incidents", []) + raw.get("Closures", []):
        if not pan(r) or ended(r, now): continue
        full = r.get("isFullClosure")
        desc = re.sub(r"\s+", " ", clean(r["description"]))[:220]
        items.append({"type": "closure" if full or r in raw.get("Closures", []) else "crash", "route": r["roadwayName"], "when": "Now",
          "where": f'{r["county"]} County', "detail": desc, "detour": clean(r.get("detourDescription")), "lat": r["lat"], "lon": r["lon"],
          "url": "https://fl511.com"})
    # major construction: full/lane closures on I-10 / US routes only
    con = [r for r in raw.get("Construction", []) if pan(r) and not ended(r, now) and r["roadwayName"] in ("I-10", "US-98", "US-90", "US-331", "US-231", "SR-85") and re.search(r"lane|closed|closure", clean(r["description"]), re.I)]
    con = [r for r in con if dist(r) <= 50 and re.search(r"(left|right|center|\d+) lane|all lanes|ramp", clean(r["description"]), re.I)][:4]
    for r in con:
        d = re.sub(r"\s+", " ", clean(r["description"]).split("Last updated")[0])[:200]
        items.append({"type": "closure", "route": r["roadwayName"], "when": "Planned", "where": f'{r["county"]} County', "detail": d, "detour": "", "lat": r["lat"], "lon": r["lon"], "url": "https://fl511.com"})
    return {"sample": False, "items": items, "emptyText": "No major closures or crashes found.",
      "emptyNote": "FL511 shows no full closures or crashes in the Panhandle right now. Alabama roads are not checked here, so look at the Alabama 511 link.",
      "links": LINKS, "updated": now.astimezone(CT).strftime("%-I:%M %p CT")}

def roads(previous=None):
    """Fresh roads section, or None if FL511 could not be read. If it cannot be read, the caller keeps the
    previous section (marked stale) instead of claiming the roads are clear."""
    now = dt.datetime.now(CT)
    try:
        return build(fetch_raw(), now)
    except Exception as e:
        print("WARN fl511", e, file=sys.stderr)
        return None

def stale_or_unavailable(previous):
    if previous and previous.get("items") is not None and previous.get("updated"):
        return dict(previous, stale=True)
    return {"sample": False, "items": [], "unavailable": True, "emptyText": "Closures and crashes are unavailable right now.",
            "emptyNote": "FL511 could not be reached. Check the FL511 and Alabama 511 links.", "links": LINKS, "updated": ""}
