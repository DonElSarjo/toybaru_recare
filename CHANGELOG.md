# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-22

This release adds provider-aware support and diagnostics developed against a 2026 Subaru Trailseeker in North America. Experimental vehicle controls remain disabled by default.

### Added
- Provider-aware remote-command capability resolution across feature, extended-capability, and remote-service-capability fields, including known horn, light, trunk, and vehicle-finder aliases.
- A dashboard capability-diagnostics panel, available with `?debug`, showing the provider context, active subscriptions, capability decision, and source field for each remote command.
- A read-only Charge Management view with remaining charging time, charging schedules, and the next charging event when supplied by the provider.
- On-demand notification and service/maintenance history views. Requests are made sequentially only when the user asks to load the data.
- `TOYBARU_EXPERIMENTAL_CHARGE_SCHEDULES`, a read-only gate for preserved Subaru NA schedule fields while their provider schema is being validated.
- Confirmation-gated experimental Charge Now and charging-schedule commands through `TOYBARU_EXPERIMENTAL_CHARGE_COMMANDS`.
- A local electric-command audit trail recording blocked, accepted, rejected, and failed requests without storing credentials.
- Provider-specific endpoint compatibility tests covering route isolation, safe fallback behavior, refresh payloads, and climate-control payloads.

### Changed
- Subaru NA now exposes its configured charging history/statistics, vehicle-health, charge-management, notification, and service-history capabilities in the dashboard while continuing to report trip history as unavailable.
- Electric commands require CSRF validation, explicit user confirmation, and a separate per-session/per-VIN rate limit. Responses are presented as asynchronous gateway acknowledgements rather than proof of vehicle execution.
- Toyota EU uses its migrated 2026 vehicle-status and climate routes, header-only status refresh, and V2 climate-control payloads.
- Legacy endpoint fallback is limited to configured Toyota EU `GET` requests that return `404`, `405`, or `410`. Authentication failures, rate limits, server errors, refreshes, and write requests never trigger fallback.
- Lexus, Subaru, and North American profiles retain independently selected endpoint versions and request formats instead of inheriting Toyota EU migrations.
- Project documentation now distinguishes Toyota NA limitations from Subaru NA capabilities and documents the experimental safety gates.

### Fixed
- Corrected remote horn and light availability when providers report `hornCapable` or `lightsCapable` instead of command-specific aliases.
- Vehicle selectors no longer display a conflicting upstream brand, such as `Lexus` for a Subaru Trailseeker. The original provider description remains available for diagnostics.
- Toyota EU climate-state handling now recognizes stopped states correctly and supports the V2 temperature object format.

### Security
- Experimental charging commands are disabled by default and require an operator-controlled environment flag.
- Every electric command requires explicit confirmation, is rate-limited, and is written to a local audit log.
- Automatic endpoint fallback is never attempted for commands or other write operations, preventing accidental duplicate vehicle actions.

### Notes
- Subaru NA charging-schedule fields and command payloads still require validation against sanitized provider fixtures before their experimental gates should be enabled.
- Immediate Stop Charging remains unimplemented because no independently confirmed provider command has been found.
- Toyota NA and Subaru NA have no configured trip-history endpoint. Subaru NA charging history/statistics are separate and remain available where returned by the provider.

## [0.2.0] - 2026-05-04

EU (Subaru Solterra) remains the primary target. NA (Toyota bZ4X) is included but best-effort.

### Added
- 9 locales: German, English (UK + US), French (FR + CA), Spanish (ES + MX), Japanese, Dutch.
- Per-language unit labels. Each locale provides a `units` namespace with metric and imperial variants (e.g. `Kilometer`/`Meilen` for German, `km/u` for Dutch). Translation strings reference them via `{distLong}`, `{speed}`, `{cityThr}` placeholders.
- Top-down vehicle SVG, server-side tinted to the car's paint colour via `/assets/car-topdown.svg?paint=<hex>`.
- Favicon set: `favicon.ico` (16/32/48 multi-res) plus PNGs at 16, 32, 48, 180, 192, 512 px.
- `toybaru trip-stats --imperial` flag.

### Changed
- No client-side unit conversion. The dashboard trusts the per-field unit the API returns (`bat.evRange.unit`, `cs.temperatureUnit`) and only swaps the displayed label.
- Frontend unit helpers: new `unitVar()` reads the locale-provided word, `tu()` does placeholder substitution. The English-only regex `localizeUnits()` is gone.
- `pyproject.toml` package-data now includes `templates/*.svg` and `templates/icons/*`.

### Fixed
- Car illustration no longer 500s in Docker (the SVG wasn't packaged).
- Non-English locales no longer leak `kilometers` / `km/h` text when the account is on miles.

### Notes
- Remote vehicle commands (lock/unlock, hatch, lights, horn, climate start/stop, find vehicle) are still in testing. They are fire-and-forget — a success response means the cloud accepted the command, not that the car executed it.
- Toyota NA still does not provide trip or charging history. The Trips, Statistics, and Data tabs auto-hide for NA accounts.

## [0.1.0]

Initial public release. EU (Subaru) and NA (Toyota) login flows, OTP/2FA, trip browser with route map and driving-mode segments, statistics dashboard, battery health graph, snapshot tracker, CSV/JSON export, German + English UI, Docker deployment.
