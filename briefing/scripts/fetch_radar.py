"""Download the NWS Eglin AFB (KEVX) radar loop. Usage: python3 fetch_radar.py <out.gif>"""
import sys, urllib.request
UA = "Mozilla/5.0 (morning-briefing)"
for name in ("KEVX_loop.gif", "KEVX_0.gif"):
    try:
        r = urllib.request.Request("https://radar.weather.gov/ridge/standard/" + name, headers={"User-Agent": UA})
        b = urllib.request.urlopen(r, timeout=30).read()
        if b[:3] == b"GIF":
            open(sys.argv[1], "wb").write(b)
            print("saved", name, len(b))
            sys.exit(0)
    except Exception as e:
        print(name, "failed:", e, file=sys.stderr)
sys.exit(1)
