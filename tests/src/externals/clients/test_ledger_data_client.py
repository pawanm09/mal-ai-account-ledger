from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.externals.clients.ledger_data_client import LedgerDataClient
from src.models.account_model import AccountModel
from src.models.entry_model import DecisionModel, EntryModel
from src.models.event_model import EventModel


@pytest.fixture
def client():
    return LedgerDataClient([
        AccountModel("ACC-001", "AED", Decimal("0.00")),
        AccountModel("ACC-002", "BHD", Decimal("0.000")),
    ])


class TestLedgerDataClient:
    def test_balance_distinguishes_value_date_from_recording_cutoff(self, client):
        client.append_entries([
            EntryModel("ACC-001", "AED", Decimal("1200"), 1, "CREDIT", "E1"),
            EntryModel("ACC-001", "AED", Decimal("-950"), 1, "DEBIT", "E2"),
            EntryModel("ACC-001", "AED", Decimal("400"), 3, "CREDIT", "E4"),
        ])
        before_backdate = client.last_sequence
        original_snapshot = client.get_records()
        client.append_entries([
            EntryModel("ACC-001", "AED", Decimal("-620"), 2, "DEBIT", "E7"),
        ])
        assert client.get_balance("ACC-001", 2, before_backdate) == Decimal("250.00")
        assert client.get_balance("ACC-001", 2) == Decimal("-370.00")
        assert client.get_balance("ACC-001", 3) == Decimal("30.00")
        assert client.get_balance("ACC-001", 1) == Decimal("250.00")
        assert client.get_records(before_backdate) == original_snapshot
        assert len(original_snapshot) == 3
        assert client.get_balance("ACC-002", 6) == Decimal("0.000")

    def test_input_attempts_and_decisions_never_change_balance(self, client):
        event = EventModel("E1", 1, "CREDIT", "ACC-001", "AED", 1, "1200.00")
        first = client.record_event(event)
        client.record_event(event)
        decision = client.record_decision(DecisionModel("E1", "ACC-001", "REJECTED", "Duplicate ID"))
        client.record_event(EventModel("BAD", 9, "UNKNOWN", "missing", "USD", 20, "NaN"))
        assert [record.sequence for record in client.get_records()] == [1, 2, 3, 4]
        assert client.get_events(1) == (first,)
        assert client.get_decisions() == (decision,)
        assert client.get_entries("ACC-001") == ()
        assert client.get_balance("ACC-001", 1) == Decimal("0.00")

    def test_snapshots_and_record_payloads_cannot_mutate_storage(self, client):
        accounts = client.get_accounts()
        client.append_entries([EntryModel("ACC-001", "AED", Decimal("1"), 1, "CREDIT", "E1")])
        records = client.get_records()
        with pytest.raises(TypeError):
            records[0] = None
        with pytest.raises(FrozenInstanceError):
            records[0].sequence = 10
        with pytest.raises(FrozenInstanceError):
            records[0].payload.amount = Decimal("999")
        with pytest.raises(TypeError):
            accounts[0] = None
        assert client.get_balance("ACC-001", 1) == Decimal("1.00")

    @pytest.mark.parametrize("bad_entry", [
        EntryModel("missing", "AED", Decimal("1"), 1, "CREDIT", "E2"),
        EntryModel("ACC-001", "BHD", Decimal("1"), 1, "CREDIT", "E2"),
        "not an entry",
    ])
    def test_batch_validation_prevents_partial_postings(self, client, bad_entry):
        before = client.get_records()
        valid = EntryModel("ACC-001", "AED", Decimal("1"), 1, "CREDIT", "E1")
        with pytest.raises(InvalidRequestException):
            client.append_entries([valid, bad_entry])
        assert client.get_records() == before
        assert client.get_balance("ACC-001", 1) == Decimal("0.00")

    def test_opening_balance_exists_at_zero_cutoff(self):
        accounts = [AccountModel("A", "BHD", Decimal("10"))]
        client = LedgerDataClient(accounts)
        accounts.clear()
        assert str(client.get_balance("A", 1, 0)) == "10.000"
        assert client.get_records(0) == ()
        assert client.append_entries([]) == ()
        assert client.last_sequence == 0

    @pytest.mark.parametrize("cutoff", [-1, 1, True, 0.5, "0"])
    def test_unknown_or_invalid_cutoff_is_rejected(self, client, cutoff):
        with pytest.raises(InvalidRequestException, match="Cutoff"):
            client.get_balance("ACC-001", 1, cutoff)

    @pytest.mark.parametrize("day", [0, 7, True, "1"])
    def test_invalid_balance_day_is_rejected(self, client, day):
        with pytest.raises(InvalidRequestException, match="Day"):
            client.get_balance("ACC-001", day)

    def test_unknown_account_and_wrong_record_types_are_rejected(self, client):
        with pytest.raises(InvalidRequestException, match="Unknown account"):
            client.get_balance("missing", 1)
        with pytest.raises(InvalidRequestException):
            client.record_event({"event_id": "E1"})
        with pytest.raises(InvalidRequestException):
            client.record_decision("ACCEPTED")

    def test_account_setup_rejects_duplicate_ids_and_wrong_record_types(self):
        account = AccountModel("A", "AED", Decimal("0"))
        with pytest.raises(InvalidRequestException, match="Duplicate account"):
            LedgerDataClient([account, account])
        with pytest.raises(InvalidRequestException):
            LedgerDataClient(["A"])
