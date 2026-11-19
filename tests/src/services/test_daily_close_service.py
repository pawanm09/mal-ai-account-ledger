from decimal import Decimal, localcontext

import pytest

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.externals.clients.ledger_data_client import LedgerDataClient
from src.models.account_model import AccountModel
from src.models.entry_model import ControlModel
from src.models.event_model import EventModel
from src.models.money import total_amounts
from src.services.daily_close_service import DailyCloseService
from src.services.ledger_service import LedgerService


@pytest.fixture
def daily():
    client = LedgerDataClient([
        AccountModel("ACC-001", "AED", Decimal("0.00")),
        AccountModel("ACC-002", "BHD", Decimal("0.000")),
    ])
    return DailyCloseService(LedgerService(client))


def event(event_id, day, kind, amount=None, value_date=None, **references):
    return EventModel(event_id, day, kind, "ACC-001", "AED",
                      day if value_date is None else value_date, amount, **references)


def fees(daily):
    return tuple(record for record in daily.ledger_data_client.get_entries("ACC-001")
                 if record.payload.kind == "FEE")


def process_through_e8(daily):
    events = [
        event("E1", 1, "CREDIT", "1200.00"),
        event("E2", 1, "DEBIT", "950.00"),
        event("E3", 2, "AUTHORIZATION", "200.00", authorization_id="Auth-A"),
        event("E4", 3, "CREDIT", "400.00"),
        event("E5", 4, "SETTLEMENT", "185.00", authorization_id="Auth-A"),
        event("E6", 4, "SETTLEMENT", "180.00", authorization_id="Auth-Z"),
        event("E7", 5, "DEBIT", "620.00", value_date=2),
        event("E8", 5, "AUTHORIZATION", "90.00", authorization_id="Auth-B"),
    ]
    return [daily.process_event(item) for item in events]


class TestDailyCloseService:
    def test_backdating_reassesses_closed_days_then_current_day_at_close(self, daily):
        results = process_through_e8(daily)
        client = daily.ledger_data_client
        assert results[4].status == "SETTLED"
        assert results[5].status == "REJECTED"
        assert results[7].status == "DECLINED"
        assert daily.closed_day == 4
        assert [record.payload.value_date for record in fees(daily)] == [2, 4]
        assert client.get_balance("ACC-001", 2) == Decimal("-395.00")
        assert client.get_balance("ACC-001", 3) == Decimal("5.00")
        assert client.get_balance("ACC-001", 4) == Decimal("-205.00")
        assert client.get_balance("ACC-001", 5) == Decimal("-205.00")
        assert daily.close_through(5)
        assert client.get_balance("ACC-001", 5) == Decimal("-230.00")
        assert [record.payload.value_date for record in fees(daily)] == [2, 4, 5]
        # Reconstruct the explicitly requested pre-fee value, without deleting fees.
        principal = [record.payload.amount for record in client.get_entries("ACC-001")
                     if record.payload.kind != "FEE" and record.payload.value_date <= 2]
        assert total_amounts(principal, "AED") == Decimal("-370.00")
        before = client.get_records()
        assert daily.reconcile()
        assert daily.close_through(5)
        assert client.get_records() == before

    def test_full_stream_retains_fees_and_capitalizes_corrected_interest(self, daily):
        process_through_e8(daily)
        client = daily.ledger_data_client
        daily.close_through(5)
        cutoff = client.last_sequence
        old_accruals = daily.daily_accruals("ACC-001", cutoff)
        original_fees = fees(daily)
        reversal = daily.process_event(event("E9", 6, "REVERSAL", value_date=2, reference_id="E7"))
        assert reversal.status == "ACCEPTED"
        assert fees(daily) == original_fees
        assert client.get_balance("ACC-001", 5) == Decimal("390.00")
        assert client.get_balance("ACC-001", 5, cutoff) == Decimal("-230.00")
        assert daily.daily_accruals("ACC-001", cutoff) == old_accruals
        e10 = EventModel("E10", 5, "CREDIT", "ACC-002", "BHD", 5, "10.000", instalments=3)
        assert daily.process_event(e10).status == "ACCEPTED"
        assert daily.closed_day == 5
        assert daily.finalize()
        expected = tuple(Decimal(amount) for amount in ("0.10", "0.09", "0.25", "0.17", "0.16", "0.16"))
        assert daily.daily_accruals("ACC-001") == expected
        assert daily.daily_accruals("ACC-002") == (Decimal("0.000"),) * 4 + (Decimal("0.004"),) * 2
        assert client.get_balance("ACC-001", 6) == Decimal("390.93")
        assert client.get_balance("ACC-002", 6) == Decimal("10.008")
        for account_id, currency in (("ACC-001", "AED"), ("ACC-002", "BHD")):
            interest = [record.payload for record in client.get_entries(account_id)
                        if record.payload.kind == "INTEREST"]
            assert len(interest) == 1
            assert interest[0].value_date == 6
            assert interest[0].amount == total_amounts(daily.daily_accruals(account_id), currency)
        assert [state.status for state in daily.ledger_service.get_authorizations("ACC-001")] == ["SETTLED", "DECLINED"]

    def test_intraday_overdraft_does_not_trigger_fee(self, daily):
        daily.process_event(event("D", 1, "DEBIT", "100.00"))
        assert fees(daily) == ()
        daily.process_event(event("C", 1, "CREDIT", "101.00"))
        assert daily.close_through(1)
        assert fees(daily) == ()
        assert daily.ledger_data_client.get_balance("ACC-001", 1) == Decimal("1.00")

    def test_zero_and_positive_closes_have_no_fee(self, daily):
        assert daily.close_through(1)
        daily.process_event(event("C", 2, "CREDIT", "1.00"))
        assert daily.close_through(2)
        assert fees(daily) == ()

    def test_negative_days_charge_once_each_including_fee_effects(self, daily):
        daily.process_event(event("D", 1, "DEBIT", "1.00"))
        daily.process_event(event("C", 2, "CREDIT", "2.00"))
        assert daily.close_through(2)
        assert daily.ledger_data_client.get_balance("ACC-001", 2) == Decimal("-49.00")
        assert [record.payload.value_date for record in fees(daily)] == [1, 2]
        before = daily.ledger_data_client.get_records()
        assert daily.close_through(2)
        assert daily.ledger_data_client.get_records() == before

    def test_holds_do_not_reduce_interest_basis(self, daily):
        daily.process_event(event("C", 1, "CREDIT", "250.00"))
        daily.process_event(event("A", 1, "AUTHORIZATION", "250.00", authorization_id="Hold"))
        assert daily.ledger_service.get_available_balance("ACC-001", 1) == Decimal("0.00")
        assert daily.finalize()
        assert daily.daily_accruals("ACC-001") == (Decimal("0.10"),) * 6
        assert daily.ledger_service.get_active_holds("ACC-001") == Decimal("250.00")
        assert daily.ledger_data_client.get_balance("ACC-001", 6) == Decimal("250.60")

    def test_daily_rounding_not_rounded_aggregate_and_no_self_interest(self, daily):
        daily.process_event(event("C", 1, "CREDIT", "12.50"))
        assert daily.finalize()
        # 0.005 each day rounds to 0.01; rounding unrounded total gives 0.03.
        assert daily.daily_accruals("ACC-001") == (Decimal("0.01"),) * 6
        assert daily.ledger_data_client.get_balance("ACC-001", 6) == Decimal("12.56")

    def test_zero_or_negative_days_earn_no_interest(self, daily):
        daily.process_event(event("D", 3, "DEBIT", "1.00"))
        assert daily.finalize()
        assert daily.daily_accruals("ACC-001") == (Decimal("0.00"),) * 6
        assert not any(record.payload.kind == "INTEREST"
                       for record in daily.ledger_data_client.get_entries("ACC-001"))

    def test_close_reconciliation_and_finalization_are_idempotent_after_reconstruction(self, daily):
        daily.process_event(event("C", 1, "CREDIT", "1000.00"))
        assert daily.finalize()
        client = daily.ledger_data_client
        before = client.get_records()
        rebuilt = DailyCloseService(LedgerService(client))
        assert rebuilt.closed_day == 6
        assert rebuilt.finalized
        assert rebuilt.finalize()
        assert rebuilt.close_through(6)
        assert rebuilt.reconcile()
        assert client.get_records() == before

    def test_finalization_rejects_new_events_through_both_service_entrypoints(self, daily):
        daily.process_event(event("C", 1, "CREDIT", "100.00"))
        assert daily.finalize()
        before = daily.ledger_data_client.get_entries("ACC-001")
        assert daily.process_event(event("LATE", 5, "DEBIT", "1.00")).status == "REJECTED"
        assert daily.ledger_service.process_event(event("DIRECT", 6, "CREDIT", "1.00")).status == "REJECTED"
        assert daily.ledger_data_client.get_entries("ACC-001") == before
        assert len(daily.ledger_data_client.get_events()) == 3

    def test_unsupported_bhd_fee_blocks_finalize_and_is_reported_once(self, daily):
        event_bhd = EventModel("D", 1, "DEBIT", "ACC-002", "BHD", 1, "1.000")
        assert daily.process_event(event_bhd).status == "ACCEPTED"
        assert not daily.finalize()
        assert not daily.finalized
        assert daily.closed_day == 0
        before = daily.ledger_data_client.get_records()
        assert not daily.finalize()
        assert daily.ledger_data_client.get_records() == before
        errors = [record.payload for record in daily.ledger_data_client.get_decisions()
                  if record.payload.status == "FEE_ERROR"]
        assert len(errors) == 1
        assert "Day 1" in errors[0].message
        correction = EventModel("R", 2, "REVERSAL", "ACC-002", "BHD", 1, reference_id="D")
        assert daily.process_event(correction).status == "ACCEPTED"
        assert daily.finalize()
        assert daily.ledger_data_client.get_balance("ACC-002", 6) == Decimal("0.000")

    def test_late_bhd_overdraft_invalidates_previously_closed_day(self, daily):
        assert daily.close_through(3)
        debit = EventModel("D", 4, "DEBIT", "ACC-002", "BHD", 2, "1.000")
        daily.process_event(debit)
        assert not daily.finalize()
        assert daily.closed_day == 3
        assert not daily.finalized

    def test_skipped_days_close_and_rejected_requests_do_not_post_fees_intraday(self, daily):
        result = daily.process_event(event("BAD", 4, "CREDIT", "NaN"))
        assert result.status == "REJECTED"
        assert daily.closed_day == 3
        assert fees(daily) == ()
        assert [control.day for control in daily.ledger_data_client.get_controls()] == [1, 2, 3]

    def test_out_of_window_event_is_audited_without_advancing_close(self, daily):
        assert daily.process_event(event("BAD", 7, "CREDIT", "1.00")).status == "REJECTED"
        assert daily.closed_day == 0

    def test_small_decimal_context_does_not_change_accruals(self, daily):
        with localcontext() as context:
            context.prec = 2
            daily.process_event(event("C", 1, "CREDIT", "12345.67"))
            assert daily.daily_accruals("ACC-001") == (Decimal("4.94"),) * 6
            assert daily.finalize()
            assert daily.ledger_data_client.get_balance("ACC-001", 6) == Decimal("12375.31")
            assert context.prec == 2

    @pytest.mark.parametrize("day", [0, 7, True, "1"])
    def test_invalid_close_day(self, daily, day):
        with pytest.raises(InvalidRequestException):
            daily.close_through(day)

    def test_invalid_input_types_and_control_markers(self, daily):
        with pytest.raises(InvalidRequestException):
            daily.process_event({})
        with pytest.raises(InvalidRequestException):
            daily.ledger_data_client.record_control("FINALIZED")
        with pytest.raises(InvalidRequestException):
            ControlModel("UNKNOWN", 1)
        with pytest.raises(InvalidRequestException):
            ControlModel("FINALIZED", 5)

    def test_explicit_closed_day_advances_authorization_clock(self, daily):
        daily.process_event(event("C", 1, "CREDIT", "1.00"))
        assert daily.close_through(5)
        assert daily.ledger_service._current_day() == 6
