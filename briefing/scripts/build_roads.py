"""Refresh only the closures and crashes in an existing data.json. Usage: build_roads.py <data.json>"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fl511
path = sys.argv[1]
data = json.load(open(path))
new = fl511.roads()
if new is None:
    print("FL511 unreachable; keeping the previous roads", file=sys.stderr)
    data["roads"] = fl511.stale_or_unavailable(data.get("roads"))
else:
    data["roads"] = new
json.dump(data, open(path + ".new", "w"), indent=1)
os.replace(path + ".new", path)
print("roads ok", len(data["roads"]["items"]), "stale" if data["roads"].get("stale") else "", file=sys.stderr)
