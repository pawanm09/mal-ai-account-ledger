from decimal import Decimal
from io import StringIO
from pathlib import Path
import subprocess
import sys

from main import day_errors, run_replay, supplied_events
from src.container import create_ledger
from src.models.event_model import EventModel


class TestReplay:
    def test_complete_replay_money_and_input_order(self):
        output = StringIO()
        daily = run_replay(output)
        client = daily.ledger_data_client
        events = [record.payload for record in client.get_events()]
        assert events == list(supplied_events())
        assert [event.event_id for event in events] == [f"E{number}" for number in range(1, 11)]
        assert events[-1].booked_day == 5
        assert events[-2].booked_day == 6
        assert client.get_balance("ACC-001", 6) == Decimal("390.93")
        assert client.get_balance("ACC-002", 6) == Decimal("10.008")
        assert daily.finalized
        assert daily.closed_day == 6
        assert [(state.authorization_id, state.status)
                for state in daily.ledger_service.get_authorizations("ACC-001")] == [
                    ("Auth-A", "SETTLED"), ("Auth-B", "DECLINED")]

    def test_output_distinguishes_original_correction_and_final_views(self):
        output = StringIO()
        run_replay(output)
        text = output.getvalue()
        assert text.count("ORIGINAL CLOSE | Day ") == 6
        assert text.count("FINAL RESTATED | Day ") == 6
        assert "CORRECTION AFTER E7 | Day 2" in text
        assert "CORRECTION AFTER E9 | Day 2" in text
        assert "CORRECTION AFTER E10 | Day 5" in text
        original_day2 = text.split("ORIGINAL CLOSE | Day 2", 1)[1].split("\nARRIVAL", 1)[0]
        assert "closing ledger AED 250.00" in original_day2
        assert "Auth-A=APPROVED" in original_day2
        corrected_day2 = text.split("CORRECTION AFTER E7 | Day 2", 1)[1].split("\nCORRECTION", 1)[0]
        assert "closing ledger AED -395.00" in corrected_day2
        assert "AED 25.00 assessed Day 2, recorded #" in corrected_day2
        assert "Auth-A=SETTLED" in corrected_day2
        assert "E6 REJECTED: Unknown authorization for this account" in text
        assert "E8 DECLINED: Insufficient available balance" in text
        assert "ACC-001 | fees AED 75.00 | capitalized AED 0.93 | final AED 390.93" in text
        assert "ACC-002 | fees BHD 0.000 | capitalized BHD 0.008 | final BHD 10.008" in text
        assert text.index("ARRIVAL E9 |") < text.index("ARRIVAL E10 |")

    def test_each_day_prints_both_accounts_and_all_required_fields(self):
        output = StringIO()
        run_replay(output)
        rows = output.getvalue().split("FINAL RESTATED | Day ")[1:]
        assert len(rows) == 6
        for day, row in enumerate(rows, 1):
            assert row.startswith(f"{day} | journal cutoff #")
            assert "ACC-001 | closing ledger AED" in row
            assert "ACC-002 | closing ledger BHD" in row
            assert row.count("Fees assessed this day:") == 2
            assert row.count("Authorization states at cutoff:") == 2
            assert row.count("Errors booked/assessed this day:") == 2
            assert row.count("Rounded daily interest:") == 2

    def test_fresh_dependency_wiring_and_repeatable_replay(self):
        first_output, second_output = StringIO(), StringIO()
        first = run_replay(first_output)
        second = run_replay(second_output)
        assert first.ledger_data_client is not second.ledger_data_client
        assert first.ledger_data_client.get_records() == second.ledger_data_client.get_records()
        assert first_output.getvalue() == second_output.getvalue()
        fresh = create_ledger()
        assert fresh.ledger_data_client.last_sequence == 0
        assert not fresh.finalized

    def test_fee_errors_are_visible_on_the_assessment_day(self):
        daily = create_ledger()
        daily.process_event(EventModel("D", 1, "DEBIT", "ACC-002", "BHD", 1, "1.000"))
        assert not daily.close_through(1)
        cutoff = daily.ledger_data_client.last_sequence
        assert "FEE_ERROR: Day 1" in day_errors(daily, "ACC-002", 1, cutoff)
        assert day_errors(daily, "ACC-002", 2, cutoff) == "none"
        assert day_errors(daily, "ACC-001", 1, cutoff) == "none"

    def test_script_runs_successfully_from_repository_root(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "main.py"], cwd=root,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert "WINDOW TOTALS" in result.stdout
        assert "final AED 390.93" in result.stdout
        assert "final BHD 10.008" in result.stdout
