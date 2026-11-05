# Claude_Morning_Briefing

Daily briefing page for dump-truck drivers in the Florida Panhandle (Mossy Head / DeFuniak Springs area).

## Layout

- `briefing/` is a Home Assistant local add-on. It serves the page and refreshes the data itself.
  - `scripts/build_data.py <out.json>` builds `data.json` (NWS weather and alerts, FL511 closures and crashes, non-political headlines).
  - `web/index.html` is the page. It reads `data.json` beside it and loads the radar (RainViewer on an Esri base map, via Leaflet) straight from the browser; if that fails the radar tile is hidden.
  - `build.sh`, `run.sh`, `Dockerfile`, `config.yaml` make up the add-on.

The add-on refreshes `data.json` at 4:30 AM Central and then every hour on the hour, around the clock, every day, and refreshes it once whenever it starts. The page reads `data.json` when it loads and does not reload itself, so reload the page to see newer data.

## Install on Home Assistant OS

1. Install the **Samba share** or **Advanced SSH & Web Terminal** add-on so you can reach the `/addons` folder.
2. Copy the `briefing` folder into `/addons/` (it ends up as `/addons/briefing/config.yaml`).
3. Settings → Add-ons → Add-on Store → ⋮ → Check for updates. A "Local add-ons" section appears with **Mossy Head Briefing**.
4. Install, then Start. Open `http://<mini-pc-address>:8099`.

To update later, replace the folder's files and use Rebuild on the add-on page.

## Security

No emails, tokens or other secrets belong in this repo. Email content is only used in the private Telegram message, never on the page. The Telegram briefing is a separate project and shares nothing with this one.
