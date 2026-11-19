from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from src.externals.clients.ledger_data_client import LedgerDataClient
from src.models.account_model import AccountModel
from src.models.event_model import EventModel
from src.services.ledger_service import LedgerService


@pytest.fixture
def service():
    return LedgerService(LedgerDataClient([
        AccountModel("ACC-001", "AED", Decimal("0.00")),
        AccountModel("ACC-002", "BHD", Decimal("0.000")),
    ]))


def credit(event_id="E1", amount="1200.00"):
    return EventModel(event_id, 1, "CREDIT", "ACC-001", "AED", 1, amount)


class TestLedgerService:
    def test_credit_and_backdated_overdrawing_debit(self, service):
        client = service.ledger_data_client
        assert service.process_event(credit()).status == "ACCEPTED"
        assert service.process_event(EventModel("E2", 1, "DEBIT", "ACC-001", "AED", 1, "950.00")).status == "ACCEPTED"
        cutoff = client.last_sequence
        decision = service.process_event(EventModel("E7", 5, "DEBIT", "ACC-001", "AED", 2, "620.00"))
        assert decision.status == "ACCEPTED"
        assert client.get_balance("ACC-001", 2, cutoff) == Decimal("250.00")
        assert client.get_balance("ACC-001", 2) == Decimal("-370.00")
        assert client.get_balance("ACC-001", 1) == Decimal("250.00")

    def test_three_bhd_instalments_conserve_total(self, service):
        event = EventModel("E10", 5, "CREDIT", "ACC-002", "BHD", 5, "10.000", instalments=3)
        assert service.process_event(event).status == "ACCEPTED"
        client = service.ledger_data_client
        postings = client.get_entries("ACC-002")
        assert [str(record.payload.amount) for record in postings] == ["3.334", "3.333", "3.333"]
        assert all(record.payload.source_event_id == "E10" for record in postings)
        assert client.get_balance("ACC-002", 4) == Decimal("0.000")
        assert client.get_balance("ACC-002", 5) == Decimal("10.000")

    def test_reversal_appends_compensation_and_preserves_original_snapshot(self, service):
        client = service.ledger_data_client
        service.process_event(EventModel("E7", 5, "DEBIT", "ACC-001", "AED", 2, "620.00"))
        before = client.get_records()
        reversal = EventModel("E9", 6, "REVERSAL", "ACC-001", "AED", 2, reference_id="E7")
        assert service.process_event(reversal).status == "ACCEPTED"
        assert client.get_records(len(before)) == before
        assert client.get_balance("ACC-001", 2, len(before)) == Decimal("-620.00")
        assert client.get_balance("ACC-001", 2) == Decimal("0.00")
        compensation = client.get_entries("ACC-001")[-1].payload
        assert compensation.amount == Decimal("620.00")
        assert compensation.reference_event_id == "E7"
        assert compensation.source_event_id == "E9"
        assert compensation.value_date == 2

    def test_full_reversal_of_instalment_credit(self, service):
        service.process_event(EventModel("C", 5, "CREDIT", "ACC-002", "BHD", 5, "10.000", instalments=3))
        result = service.process_event(EventModel("R", 6, "REVERSAL", "ACC-002", "BHD", 5, reference_id="C"))
        assert result.status == "ACCEPTED"
        postings = service.ledger_data_client.get_entries("ACC-002")
        assert len(postings) == 4
        assert postings[-1].payload.amount == Decimal("-10.000")
        assert service.ledger_data_client.get_balance("ACC-002", 6) == Decimal("0.000")

    def test_duplicate_attempt_is_retained_without_second_effect(self, service):
        service.process_event(credit())
        result = service.process_event(credit(amount="1.00"))
        assert result.status == "REJECTED"
        assert result.message == "Duplicate event ID"
        client = service.ledger_data_client
        assert len(client.get_events()) == 2
        assert len(client.get_entries("ACC-001")) == 1
        assert client.get_balance("ACC-001", 1) == Decimal("1200.00")

    def test_rejected_first_attempt_reserves_its_event_id(self, service):
        assert service.process_event(credit(amount="NaN")).status == "REJECTED"
        assert service.process_event(credit()).message == "Duplicate event ID"
        assert service.ledger_data_client.get_entries("ACC-001") == ()

    @pytest.mark.parametrize("changes", [
        {"event_id": ""}, {"account_id": "missing"}, {"currency": "BHD"},
        {"amount": "NaN"}, {"amount": "Infinity"}, {"amount": "invalid"},
        {"amount": None}, {"amount": "0"}, {"amount": "-1.00"}, {"amount": "1.001"},
        {"booked_day": 0}, {"booked_day": 7}, {"value_date": 0}, {"value_date": 7},
        {"booked_day": 1, "value_date": 2}, {"kind": "UNKNOWN"},
        {"instalments": 0}, {"instalments": -1}, {"amount": "0.01", "instalments": 2},
        {"kind": "DEBIT", "instalments": 2}, {"authorization_id": "Auth-A"},
        {"reference_id": "other"},
    ])
    def test_rejected_requests_are_audited_without_postings(self, service, changes):
        event = replace(credit(), **changes)
        result = service.process_event(event)
        client = service.ledger_data_client
        assert result.status == "REJECTED"
        assert client.get_events()[0].payload == event
        assert client.get_decisions()[0].payload == result
        assert client.get_entries("ACC-001") == ()
        assert client.get_entries("ACC-002") == ()
        assert client.last_sequence == 2

    @pytest.mark.parametrize("changes", [
        {"reference_id": None}, {"reference_id": "missing"}, {"reference_id": "R"},
        {"value_date": 2}, {"amount": "1200.00"},
        {"account_id": "ACC-002", "currency": "BHD"},
    ])
    def test_invalid_reversal_has_no_financial_effect(self, service, changes):
        service.process_event(credit())
        client = service.ledger_data_client
        before = client.get_entries("ACC-001")
        event = EventModel("R", 6, "REVERSAL", "ACC-001", "AED", 1, reference_id="E1")
        assert service.process_event(replace(event, **changes)).status == "REJECTED"
        assert client.get_entries("ACC-001") == before
        assert client.get_entries("ACC-002") == ()

    def test_second_reversal_and_reversal_of_reversal_are_rejected(self, service):
        service.process_event(credit())
        reversal = EventModel("R1", 6, "REVERSAL", "ACC-001", "AED", 1, reference_id="E1")
        assert service.process_event(reversal).status == "ACCEPTED"
        assert service.process_event(replace(reversal, event_id="R2")).message == "Event has already been reversed"
        result = service.process_event(replace(reversal, event_id="R3", reference_id="R1"))
        assert result.status == "REJECTED"
        assert len(service.ledger_data_client.get_entries("ACC-001")) == 2

    def test_reversal_of_rejected_event_is_rejected(self, service):
        service.process_event(credit(amount="bad"))
        result = service.process_event(EventModel("R", 6, "REVERSAL", "ACC-001", "AED", 1, reference_id="E1"))
        assert result.status == "REJECTED"
        assert service.ledger_data_client.get_entries("ACC-001") == ()

    def test_large_debit_and_reversal_keep_precision_under_small_context(self, service):
        amount = "9999999999999999999999999999.99"
        with localcontext() as context:
            context.prec = 3
            debit = EventModel("D", 1, "DEBIT", "ACC-001", "AED", 1, amount)
            assert service.process_event(debit).status == "ACCEPTED"
            assert str(service.ledger_data_client.get_balance("ACC-001", 1)) == "-" + amount
            reversal = EventModel("R", 2, "REVERSAL", "ACC-001", "AED", 1, reference_id="D")
            assert service.process_event(reversal).status == "ACCEPTED"
            assert str(service.ledger_data_client.get_balance("ACC-001", 2)) == "0.00"
