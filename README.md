# Toybaru ReCare

A self-hosted dashboard for the Subaru Solterra and Toyota bZ4X that gives you access to your own driving data -- the data that Subaru and Toyota collect but never show you.

Primary target is **EU (Subaru Solterra on SubaruConnect)**. NA (Toyota bZ4X on Toyota Connected Services) is supported for login and the parts of the API that work, but is best-effort -- see the notes below.

## Why this exists

I built this because Subaru silently deleted all my trip data from 2024. One day it was there, the next it was gone. No warning, no export option, no backup. Almost a year of driving history, just wiped from their servers.

That pissed me off enough to start poking around the SubaruConnect API. What I found was surprising: the API collects far more data than the app ever shows you. For every single trip, Subaru tracks:

- **Overspeed logging** -- every point on your route where you exceeded the speed limit is flagged with `overspeed: true`. Subaru knows exactly where and when you were speeding. This is never shown in the app.
- **Driving behaviour events** -- every hard brake, every aggressive acceleration is logged with GPS coordinates, timestamps, severity scores, and even road gradient. The app shows you a vague "driving score" but never the raw events.
- **Driving mode per route point** -- every few meters, the car records whether you were in Eco, Power, or Regeneration mode. The full route is reconstructed with mode-colored segments.

None of this is visible in the Subaru Care app. Your car is basically a telemetry device on wheels, and you have no access to your own data.

So I built a dashboard around it. Import your trips, store them locally (so Subaru can't delete them again), browse your routes on a map, see where you braked hard, check your efficiency stats, and export everything as CSV or JSON.

## Screenshots

<details>
<summary>Click to expand screenshots</summary>

<img src="screenshots/vehicle.jpg" alt="Vehicle overview" width="700">

<img src="screenshots/trips.jpg" alt="Trip browser" width="700">

<img src="screenshots/trip-detail.jpg" alt="Trip detail" width="500">

<img src="screenshots/route-map.jpg" alt="Route map with driving modes" width="700">

<img src="screenshots/statistics.jpg" alt="Statistics dashboard" width="700">

<img src="screenshots/data-import.jpg" alt="Data import and export" width="700">

</details>

## Features

**Vehicle Overview**
- Battery state of charge, range (with and without climate), charging status
- Battery bar color-coded for EV-optimal range: green (10-80%), yellow (>80%, wear risk), red (<10%, low)
- Charger level detection (Level 1 / Level 2 / DC Fast L3) with kW rate, estimated full time, and raw chargeType code
- Vehicle hero card with official Toyota/Subaru render image, color, nickname, and model info
- Manufactured date and first-use date
- Vehicle capabilities shown as badges (Digital Key, Solar Panel, Apple CarPlay, Android Auto, etc.)
- Active subscription tracker with color-coded expiry dates (green >1yr, yellow <1yr, red <90 days)
- HVAC climate preset settings displayed in Remote Controls (temperature, blower, defoggers)
- Door/window/hatch lock status with open/closed indicators
- Last known GPS position on a map
- Top-down vehicle illustration on the start page, tinted to match your car's actual paint colour
- Remote controls (still in testing -- see notes): lock/unlock doors, lock/unlock hatch, headlights on/off, hazard lights on/off, sound horn, buzzer warning, engine start/stop, find vehicle
- Unit labels follow the upstream account setting (km/h vs mph, °C vs °F). The dashboard never converts values -- it only shows the unit string the API reports.
- Date/time format adapts to region (DD/MM/YYYY 24h for EU; MM/DD/YYYY 12h AM/PM for NA)
- Last trip summary with key metrics (EU only -- see note below)

**Battery Health**
- Battery health graph tracking SOC % and estimated range over time
- Charging session indicators on the graph (green dots when plugged in)
- Lifetime charge session counter from Toyota's plugInHistory field
- Estimated energy throughput calculation (based on charge cycles and battery capacity)
- Charge frequency tracking (sessions per month since first use)
- All data logged locally via snapshot tracker for long-term degradation analysis

**OTP / Two-Factor Authentication**
- Full support for Toyota NA's ForgeRock OTP flow
- OTP codes are delivered via email (check spam/junk if not received)
- Two-phase login: enter credentials → enter OTP code → dashboard loads
- Works with both the web dashboard and CLI

**Trip Browser**
- All trips in a sortable, filterable table
- Date range selection
- Score badges (color-coded: green >80, yellow >60, red <60)
- Eco/Regeneration/Power distribution per trip as stacked bar
- Hard braking and acceleration event counts
- Click any trip for the detail view

**Trip Detail View**
- Interactive zoomable map with the driven route
- Route colored by driving mode (green=Eco, blue=Regeneration, red=Power)
- Start and end markers
- Braking and acceleration events as colored dots on the map
- Hover tooltips showing mode, overspeed status, and coordinates
- Score breakdown (overall, acceleration, braking, consistency)
- Driving behaviour event table with timestamps and ratings
- Raw JSON view ("Stats for Nerds")

**Statistics**
- Time range filter (any date range or all-time)
- Total trips, kilometers, hours driven, km per day
- Average and max speed, average scores (overall, acceleration, braking)
- Eco/Regeneration/Power efficiency breakdown with stacked bar
- Monthly km bar chart with score trend
- Trips by weekday and time of day (24h histogram)
- Speed category breakdown (city <40, rural 40-80, highway >80 km/h)
- Score distribution histogram
- Idle time, overspeed km, night trip percentage
- Records: longest trip, top speed, best score, best regeneration, most km in a day

**Data Management**
- Import all historical trips from the Subaru API with live progress log
- Incremental sync (fetch only new trips since last import)
- Export trips as CSV (structured columns) or JSON (including route and behaviour data)
- Re-import from a previously exported JSON file (UPSERT, no duplicates)
- Local SQLite database -- your data stays on your machine

**Security**
- CSRF protection on all state-changing endpoints
- Authentication required on all data/export endpoints
- No plaintext password storage -- only username and region are saved locally
- PKCE S256 for OAuth2 authorization code flow
- JWT signature verification via ForgeRock JWKS
- Sanitized error messages (detailed errors logged server-side only)
- XSS hardening (textContent for dynamic content, no inline handlers with user data)
- Security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- Rate limiting on login, OTP, and vehicle command endpoints
- Session expiry with automatic cleanup
- VIN format validation
- Docker container runs as non-root user

**Toyota NA Region Support**
- Full Toyota North America API integration alongside existing Subaru EU
- Automatic endpoint and header adaptation per region
- Battery data normalization (NA format → standard format)
- plugStatus mapping (including codes 4, 12, 40, 45) with connectorStatus fallback
- HVAC climate settings extracted from electric status endpoint
- Vehicle info: image, color, nickname, capabilities, subscriptions, manufactured/first-use dates
- Solar panel status detection (equipped vs N/A)
- Charge cycle tracking via plugInHistory counter
- Trips, Statistics, and Data tabs automatically hidden for NA users (Toyota NA does not provide trip or charging history data)
- Unit display follows the API's per-field unit (e.g. miles/mph for a NA account, km/km/h for an EU account) -- no client-side conversion

**Multi-language**
- 9 locales: German (`de`), English UK (`en`), English US (`en-US`), Spanish ES (`es-ES`), Spanish MX (`es-MX`), French FR (`fr-FR`), French CA (`fr-CA`), Japanese (`ja-JP`), Dutch (`nl-NL`)
- Each locale ships its own metric/imperial unit words (e.g. `Kilometer`/`Meilen` in German, `km/u` in Dutch). Translation strings reference them via `{distLong}`, `{speed}`, `{cityThr}` placeholders -- the dashboard substitutes the right one based on the API account's unit setting.
- Add more languages by dropping a JSON file into the locales directory
- Language switcher dropdown, preference saved in browser

**Auto-Sync**
- Configurable automatic data refresh: Off, 1, 5, 15, 30, or 60 minute intervals
- Preference saved in browser and persists across sessions

**Brand-Aware Theming**
- Light and dark mode toggle, saved in browser
- Theme colors automatically match your brand: Toyota Red or Subaru Blue
- Inspired by the official Toyota and MySubaru iOS apps
- Brand is auto-detected from your login, or previewed when selecting a brand on the login screen

**Multi-vehicle**
- Vehicle switcher in the top bar
- All data stored per VIN
- Works if your account has multiple vehicles linked

## Installation

### Docker (recommended)

```bash
git clone https://github.com/youruser/toybaru.git
cd toybaru
docker compose up -d
```

Open http://localhost:8099, sign in with your Subaru or Toyota account credentials. Toyota NA users will be prompted for an OTP code delivered via email.

Your data is stored in a Docker volume (`toybaru-data`). It persists across container restarts and rebuilds.

### Local (Python)

Requires Python 3.10+.

```bash
git clone https://github.com/youruser/toybaru.git
cd toybaru
python -m venv .venv
source .venv/bin/activate
pip install .
toybaru dashboard
```

Open http://127.0.0.1:8099.

Alternatively, you can use the CLI directly:

```bash
toybaru login -r EU
toybaru vehicles
toybaru status <VIN>
toybaru battery <VIN>
toybaru trips <VIN> --from 2025-01-01 --json
toybaru import-trips <VIN> --from 2024-06-01
toybaru trip-stats
toybaru raw GET /v2/vehicle/guid
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `TOYBARU_DATA_DIR` | `~/.config/toybaru` | Directory for databases, tokens, and config |
| `TOYBARU_SECURE_COOKIES` | `false` | Set to `true` to require HTTPS for session cookies (auto-detected if behind a reverse proxy with `X-Forwarded-Proto: https`) |

## Configuration

### Region config

The tool ships with EU (Europe) and NA (North America) configurations. These are the API endpoints, client IDs, and authentication realms needed to talk to the Subaru/Toyota backend.

To override or add regions, create a `regions.json` file in your data directory:

```bash
# Docker
docker compose cp regions.example.json toybaru:/data/regions.json

# Local
cp regions.example.json ~/.config/toybaru/regions.json
```

Edit the file to change values. You only need to include the fields you want to override -- missing fields fall back to the built-in defaults. See `regions.example.json` for the full structure.

### Adding a language

Create a new JSON file in `src/toybaru/locales/`, for example `fr.json`:

```json
{
  "_meta": {
    "locale": "fr-FR",
    "label": "Francais"
  },
  "app": {
    "name": "Toybaru ReCare",
    ...
  }
}
```

Use `en.json` as a template. The language will appear automatically in the dropdown after restarting the server.

## First steps after installation

1. Open the dashboard and sign in with your Subaru or Toyota account (same credentials as the SubaruConnect / Toyota app)
2. Toyota NA users: enter the OTP code sent to your email (check spam/junk folder -- codes come from `donotreply@toyotaconnectedservices.com` for Toyota or `noreply@subaruconnectedservices.io` for Subaru)
3. **EU users:** Go to the **Data** tab, set the "From" date to when you got your car and click **Start import**
4. Wait for the import to finish (about 1 minute per 100 trips)
5. Go to **Trips** to browse your data, **Statistics** for the overview
6. **NA users:** Trip and charging history data is not available from Toyota's API. The Vehicle tab shows battery, status, location, and remote controls.

After the initial import, use the **Fetch new trips** button on the Trips tab to pull only the latest data.

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Important notes

- **Tested on a 2023 Subaru Solterra (EU / Germany) and a 2026 Toyota bZ4X XLE FWD PLUS (NA / US).** EU is the primary target. Other regions may work but are untested.
- **Remote commands are still in testing.** They are wired up end-to-end and will return success when the cloud accepts the command, but they are fire-and-forget: the car has to wake up to actually execute them (15-60s). Availability varies by model and region. Treat a success response as "cloud accepted", not "car did it".
- **Toyota NA uses OTP via email for authentication.** The codes arrive from `donotreply@toyotaconnectedservices.com` (Toyota) or `noreply@subaruconnectedservices.io` (Subaru) and may land in your spam folder.
- **Toyota NA does not provide trip or charging history data.** Neither trip logs nor charging session history are available through Toyota's North America API. The Trips, Statistics, and Data tabs are automatically hidden for NA users. Only vehicle status, battery, location, and remote controls are available.
- **Subaru deletes trip data after approximately 12 months.** This is why local storage matters. Import your data regularly.
- **The API does not provide kWh consumption per trip.** The endpoints for energy data exist but return 403 (Forbidden) for the Subaru API client.
- **No official API documentation exists.** This project is based on reverse-engineering the mobile apps and community research (see Credits).

## Running tests

```bash
pip install -e ".[test]"
pytest tests/ -v
```

## Contributing

This project is tested with one car in one country. If you have a Solterra or bZ4X in a different region and want to help, contributions are welcome:

- Verify and fix region configurations for other markets (Japan, Australia, etc.)
- Add translations (just create a new JSON file in `src/toybaru/locales/`)
- Report what works and what doesn't on your vehicle
- Help discover additional Toyota NA API endpoints (trips, charging history)

Open an issue or pull request on GitHub.

## License

This project is licensed under the GNU General Public License.
See [LICENSE](LICENSE) for the full text.

## AI Disclaimer

This project was built with assistance from AI. All code was reviewed by the author.

## Credits

- [angryhussord/toybaru_recare](https://github.com/angryhussord/toybaru_recare) -- auth code (login, OAuth/PKCE, ForgeRock token exchange, session handling) was taken from here
- [evcc](https://github.com/evcc-io/evcc) -- original reverse-engineering of the Subaru EU login flow
- [toyotactl](https://github.com/spotlightishere/toyotactl) -- Toyota NA ForgeRock OTP/2FA flow, devicePrint payload, token-exchange sequence
- [pytoyoda](https://github.com/pytoyoda/pytoyoda) -- Toyota Connected Europe API reference and data models
- [ha-toyota-na](https://github.com/widewing/ha-toyota-na) -- API gateway URL, API key, and endpoint paths for Toyota NA
- [toyota-na](https://pypi.org/project/toyota-na/) -- remote command payloads, telemetry endpoints, GENERATION header format
- [SolterraWidget](https://github.com/RossGGG/SolterraWidget) -- NA endpoint and auth-flow verification
- [myToyota](https://github.com/Noyax-37/myToyota) -- climate-settings, climate-control, ac-reservation endpoints
- [tojota](https://github.com/calmjm/tojota) -- plugInHistory and plugStatus decoding
- OpenStreetMap contributors -- map tiles
