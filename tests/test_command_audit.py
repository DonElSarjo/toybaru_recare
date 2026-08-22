"""Local electric-command audit storage tests."""

from toybaru.command_audit import get_commands, log_command


def test_command_audit_round_trip_hides_request_body(tmp_path, monkeypatch):
    monkeypatch.setattr("toybaru.database.DATA_DIR", tmp_path)
    audit_id = log_command(
        vin="JF2ABCDE6GH123456",
        command="SET_CHARGING_TIME",
        request={"reservationCharge": {"day": "MONDAY"}},
        outcome="accepted",
        response_code="000000",
        response_summary="Gateway acknowledged request",
    )

    rows = get_commands(vin="JF2ABCDE6GH123456")

    assert rows[0]["id"] == audit_id
    assert rows[0]["command"] == "SET_CHARGING_TIME"
    assert rows[0]["outcome"] == "accepted"
    assert "request_json" not in rows[0]
