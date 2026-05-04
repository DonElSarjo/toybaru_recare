# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
