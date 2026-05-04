"""CLI for Subaru Solterra Connected Services."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from toybaru.client import ToybaruClient
from toybaru.const import DATA_DIR, REGIONS
from toybaru.exceptions import OtpRequiredError

console = Console()
CREDS_FILE = DATA_DIR / "credentials.json"


def _load_creds() -> dict | None:
    if CREDS_FILE.exists():
        try:
            return json.loads(CREDS_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def _save_creds(username: str, region: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(json.dumps({"username": username, "region": region}, indent=2))


def _get_client(username: str | None, password: str | None, region: str | None) -> ToybaruClient:
    """Build client from explicit args or saved credentials."""
    creds = _load_creds()
    if not username and creds:
        username = creds.get("username")
    if not region and creds:
        region = creds.get("region", "EU")
    if not region:
        region = "EU"

    if not username:
        console.print("[red]No credentials. Run 'toybaru login' first.[/red]")
        sys.exit(1)

    if not password:
        try:
            import keyring
            password = keyring.get_password("toybaru", username)
        except Exception:
            pass

    if not password:
        console.print("[red]No password found. Run 'toybaru login' first.[/red]")
        sys.exit(1)

    return ToybaruClient(username=username, password=password, region=region)


def _run(coro):
    return asyncio.run(coro)


def _print_json(data, output_json: bool = False):
    if output_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        console.print(JSON(json.dumps(data, default=str)))


@click.group()
@click.version_option(package_name="toybaru")
def main():
    """toybaru - Subaru Solterra Connected Services CLI."""
    pass


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8099, help="Port to bind to")
def dashboard(host: str, port: int):
    """Start the web dashboard."""
    from toybaru.web import run
    console.print(f"[bold]Dashboard:[/bold] http://{host}:{port}")
    run(host=host, port=port)


@main.command(name="import-trips")
@click.argument("vin")
@click.option("--from", "from_date", type=click.DateTime(formats=["%Y-%m-%d"]),
              default="2020-01-01", help="Start date")
@click.option("--to", "to_date", type=click.DateTime(formats=["%Y-%m-%d"]),
              default=str(date.today()), help="End date")
@click.option("--batch-size", default=5, help="Trips per API request (max 5)")
@click.option("--with-route", is_flag=True, help="Include route data (slower, more data)")
def import_trips(vin: str, from_date, to_date, batch_size: int, with_route: bool):
    """Import all historical trip data into local database.

    Paginates through all trips and stores them in SQLite.
    Safe to re-run - uses UPSERT (trip ID as unique key).
    """
    from toybaru.trip_store import upsert_trips, get_trip_count

    client = _get_client(None, None, None)
    fd = from_date.date() if hasattr(from_date, 'date') else from_date
    td = to_date.date() if hasattr(to_date, 'date') else to_date

    console.print(f"[bold]Importing trips[/bold] {fd} to {td}, VIN {vin}")
    console.print(f"DB before: {get_trip_count()} trips")

    offset = 0
    total_new = 0
    total_updated = 0
    total_fetched = 0

    while True:
        data = _run(client.get_trips(
            vin,
            from_date=fd,
            to_date=td,
            route=with_route,
            summary=True,
            limit=batch_size,
            offset=offset,
        ))

        payload = data.get("payload", data)
        trips = payload.get("trips", [])
        meta = payload.get("_metadata", {}).get("pagination", {})
        total_count = meta.get("totalCount", "?")

        if not trips:
            break

        new, updated = upsert_trips(trips)
        total_new += new
        total_updated += updated
        total_fetched += len(trips)

        console.print(f"  Offset {offset}: {len(trips)} trips ({new} new, {updated} updated) [{total_fetched}/{total_count}]")

        next_offset = meta.get("nextOffset")
        if next_offset is None or next_offset <= offset:
            break
        offset = next_offset

    console.print(f"\n[green]Done.[/green] Fetched {total_fetched}, new {total_new}, updated {total_updated}")
    console.print(f"DB now: {get_trip_count()} trips")


@main.command(name="trip-stats")
@click.option("--imperial", is_flag=True, help="Show imperial units (mi/mph) instead of metric (km/km/h).")
def trip_stats(imperial: bool):
    """Show statistics from the local trip database."""
    from toybaru.trip_store import get_stats, get_trip_count

    stats = get_stats()
    if stats["total_trips"] == 0:
        console.print("[yellow]No trips in database. Run 'toybaru import-trips <VIN>' first.[/yellow]")
        return

    dist = "mi" if imperial else "km"
    spd = "mph" if imperial else "km/h"

    table = Table(title=f"Trip Statistics ({stats['total_trips']} trips)")
    table.add_column("Metric", style="dim")
    table.add_column("Value")
    table.add_row("Total Distance", f"{stats['total_km']} {dist}")
    table.add_row("Total Time", f"{stats['total_hours']} h")
    table.add_row("Avg Speed", f"{stats['avg_speed']} {spd}")
    table.add_row("Max Speed", f"{stats['max_speed']} {spd}")
    table.add_row("Avg Score", f"{stats['avg_score']}")
    table.add_row("First Trip", stats['first_trip'] or '?')
    table.add_row("Last Trip", stats['last_trip'] or '?')
    table.add_row("Rekuperation", f"{stats['reku_pct']}%")
    table.add_row("Eco-Anteil", f"{stats['eco_pct']}%")
    table.add_row("Power-Anteil", f"{stats['power_pct']}%")
    console.print(table)


@main.command()
@click.option("--username", "-u", prompt="Email/Username", help="Account email")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Account password")
@click.option("--region", "-r", type=click.Choice(list(REGIONS.keys())), default="EU", help="Region")
def login(username: str, password: str, region: str):
    """Authenticate with Subaru/Toyota Connected Services."""
    try:
        import keyring
        keyring.set_password("toybaru", username, password)
    except Exception:
        console.print("[yellow]Warning: Could not save password to keyring. "
                      "You'll need to provide it each time.[/yellow]")

    _save_creds(username, region)

    client = ToybaruClient(username=username, password=password, region=region)
    try:
        uuid = _run(client.login())
        console.print(f"[green]Login successful.[/green] UUID: {uuid}")

        vehicles = _run(client.get_vehicles())
        if vehicles:
            table = Table(title="Vehicles")
            table.add_column("VIN", style="cyan")
            table.add_column("Name")
            table.add_column("Model")
            for v in vehicles:
                table.add_row(v.vin or "?", v.alias or "-", v.model_description or "-")
            console.print(table)
        else:
            console.print("[yellow]No vehicles found.[/yellow]")
    except OtpRequiredError:
        code = click.prompt("Enter the OTP code sent to your device")
        try:
            uuid = _run(client.submit_otp(code))
            console.print(f"[green]Login successful.[/green] UUID: {uuid}")
        except Exception as e:
            console.print(f"[red]OTP verification failed: {e}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("vin")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def status(vin: str, output_json: bool):
    """Get vehicle status (doors, windows, odometer)."""
    client = _get_client(None, None, None)
    data = _run(client.get_vehicle_status(vin))
    _print_json(data, output_json)


@main.command()
@click.argument("vin")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def battery(vin: str, output_json: bool):
    """Get EV battery and charging status."""
    client = _get_client(None, None, None)
    data = _run(client.get_electric_status(vin))
    _print_json(data, output_json)


@main.command()
@click.argument("vin")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def location(vin: str, output_json: bool):
    """Get last known vehicle location."""
    client = _get_client(None, None, None)
    data = _run(client.get_location(vin))
    _print_json(data, output_json)


@main.command()
@click.argument("vin")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def telemetry(vin: str, output_json: bool):
    """Get telemetry data (odometer, energy)."""
    client = _get_client(None, None, None)
    data = _run(client.get_telemetry(vin))
    _print_json(data, output_json)


@main.command()
@click.argument("vin")
@click.option("--from", "from_date", type=click.DateTime(formats=["%Y-%m-%d"]),
              default=str(date.today() - timedelta(days=30)), help="Start date (YYYY-MM-DD)")
@click.option("--to", "to_date", type=click.DateTime(formats=["%Y-%m-%d"]),
              default=str(date.today()), help="End date (YYYY-MM-DD)")
@click.option("--route", is_flag=True, help="Include route coordinates")
@click.option("--limit", default=50, help="Max trips to return")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def trips(vin: str, from_date, to_date, route: bool, limit: int, output_json: bool):
    """Get trip history."""
    client = _get_client(None, None, None)
    data = _run(client.get_trips(
        vin,
        from_date=from_date.date() if hasattr(from_date, 'date') else from_date,
        to_date=to_date.date() if hasattr(to_date, 'date') else to_date,
        route=route,
        limit=limit,
    ))
    _print_json(data, output_json)


@main.command()
@click.argument("vin")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def notifications(vin: str, output_json: bool):
    """Get notification history."""
    client = _get_client(None, None, None)
    data = _run(client.get_notifications(vin))
    _print_json(data, output_json)


@main.command(name="service-history")
@click.argument("vin")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def service_history(vin: str, output_json: bool):
    """Get service history."""
    client = _get_client(None, None, None)
    data = _run(client.get_service_history(vin))
    _print_json(data, output_json)


@main.command()
@click.argument("vin")
def refresh(vin: str):
    """Request fresh status update from vehicle."""
    client = _get_client(None, None, None)
    data = _run(client.refresh_status(vin))
    console.print(f"Refresh requested: {json.dumps(data, default=str)}")
    data_ev = _run(client.refresh_electric_status(vin))
    console.print(f"EV refresh requested: {json.dumps(data_ev, default=str)}")


@main.command()
@click.argument("vin")
@click.argument("command_name", metavar="COMMAND",
                type=click.Choice(["door-lock", "door-unlock", "engine-start", "engine-stop"]))
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def command(vin: str, command_name: str, output_json: bool):
    """Send remote command to vehicle."""
    client = _get_client(None, None, None)
    data = _run(client.send_command(vin, command_name))
    _print_json(data, output_json)


@main.command()
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def account(output_json: bool):
    """Get account information."""
    client = _get_client(None, None, None)
    data = _run(client.get_account())
    _print_json(data, output_json)


@main.command()
def vehicles():
    """List all vehicles linked to your account."""
    client = _get_client(None, None, None)
    vehicles_list = _run(client.get_vehicles())
    if not vehicles_list:
        console.print("[yellow]No vehicles found.[/yellow]")
        return
    table = Table(title="Vehicles")
    table.add_column("VIN", style="cyan")
    table.add_column("Name")
    table.add_column("Model")
    for v in vehicles_list:
        table.add_row(v.vin or "?", v.alias or "-", v.model_description or "-")
    console.print(table)


@main.command()
@click.argument("method", type=click.Choice(["GET", "POST", "PUT", "DELETE"]))
@click.argument("endpoint")
@click.option("--vin", default=None, help="VIN to include in headers")
def raw(method: str, endpoint: str, vin: str | None):
    """Make a raw API request to any endpoint.

    Examples:

        toybaru raw GET /v2/vehicle/guid

        toybaru raw GET /v1/global/remote/status --vin JTMXXXXXXXX

        toybaru raw GET /v3/telemetry --vin JTMXXXXXXXX
    """
    client = _get_client(None, None, None)
    resp = _run(client.raw_request_full(method, endpoint, vin=vin))
    console.print(f"[bold]HTTP {resp.status_code}[/bold]")
    console.print("[dim]Headers:[/dim]")
    for k, v in resp.headers.items():
        console.print(f"  {k}: {v}")
    console.print()
    if resp.content:
        try:
            console.print(JSON(resp.text))
        except Exception:
            console.print(resp.text)


@main.command()
@click.argument("vin")
@click.option("--from", "from_date", type=click.DateTime(formats=["%Y-%m-%d"]),
              default=str(date.today() - timedelta(days=30)))
@click.option("--to", "to_date", type=click.DateTime(formats=["%Y-%m-%d"]),
              default=str(date.today()))
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path")
def export(vin: str, from_date, to_date, fmt: str, output: str | None):
    """Export all vehicle data to JSON or CSV."""
    client = _get_client(None, None, None)

    console.print("[bold]Collecting data...[/bold]")

    data = {
        "vin": vin,
        "exported_at": str(date.today()),
        "status": _run(client.get_vehicle_status(vin)),
        "electric": _run(client.get_electric_status(vin)),
        "location": _run(client.get_location(vin)),
        "telemetry": _run(client.get_telemetry(vin)),
        "trips": _run(client.get_trips(
            vin,
            from_date=from_date.date() if hasattr(from_date, 'date') else from_date,
            to_date=to_date.date() if hasattr(to_date, 'date') else to_date,
            route=True,
        )),
        "notifications": _run(client.get_notifications(vin)),
    }

    if fmt == "json":
        result = json.dumps(data, indent=2, default=str)
        if output:
            Path(output).write_text(result)
            console.print(f"[green]Exported to {output}[/green]")
        else:
            click.echo(result)
    elif fmt == "csv":
        import csv
        import io

        trips_data = data.get("trips", {})
        trips_list = trips_data.get("trips", []) if isinstance(trips_data, dict) else []

        buf = io.StringIO()
        if trips_list:
            writer = csv.DictWriter(buf, fieldnames=trips_list[0].keys() if trips_list else [])
            writer.writeheader()
            for trip in trips_list:
                flat = {}
                for k, v in trip.items():
                    flat[k] = json.dumps(v, default=str) if isinstance(v, (dict, list)) else v
                writer.writerow(flat)

        csv_content = buf.getvalue()
        if output:
            Path(output).write_text(csv_content)
            console.print(f"[green]Exported {len(trips_list)} trips to {output}[/green]")
        else:
            click.echo(csv_content)


@main.command()
def logout():
    """Clear saved credentials and tokens."""
    from toybaru.auth.controller import AuthController, TOKEN_FILE

    creds = _load_creds()  # before files get deleted below

    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    if CREDS_FILE.exists():
        CREDS_FILE.unlink()

    meta_file = DATA_DIR / "session_meta.json"
    if meta_file.exists():
        meta_file.unlink()

    if creds and creds.get("username"):
        try:
            import keyring
            keyring.delete_password("toybaru", creds["username"])
        except Exception:
            pass

    console.print("[green]Logged out. Credentials and tokens cleared.[/green]")


if __name__ == "__main__":
    main()
