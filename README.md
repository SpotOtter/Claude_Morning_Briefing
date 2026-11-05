# Claude_Morning_Briefing

Daily briefing for dump-truck drivers in the Florida Panhandle (Mossy Head / DeFuniak Springs area).

- `scripts/build_data.py <out.json>` builds `data.json` (NWS weather and alerts, FL511 closures and crashes, non-political headlines).
- `scripts/fetch_radar.py <out.gif>` downloads the NWS Eglin AFB radar loop.
- `web/index.html` is the page; it reads `data.json` and `radar.gif` beside it.

Scheduled tasks (weekdays, Central): 4:30 AM page data, 4:38 AM radar, 4:45 AM Telegram message.

No emails, tokens or other secrets belong in this repo. Email content is only used in the private Telegram message, never on the page.
