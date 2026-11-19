from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.models.account_model import AccountModel
from src.models.entry_model import DecisionModel, EntryModel
from src.models.event_model import EventModel


class TestLedgerModels:
    def test_records_are_immutable_and_normalize_only_on_construction(self):
        account = AccountModel("ACC-001", "AED", Decimal("0"))
        entry = EntryModel("ACC-001", "AED", Decimal("1"), 1, "CREDIT", "E1")
        event = EventModel("E1", 1, "CREDIT", "ACC-001", "AED", 1, "1.00")
        decision = DecisionModel("E1", "ACC-001", "ACCEPTED", "Credit accepted")
        assert str(account.opening_balance) == "0.00"
        assert str(entry.amount) == "1.00"
        for record, field in [(account, "currency"), (entry, "amount"),
                              (event, "amount"), (decision, "status")]:
            with pytest.raises(FrozenInstanceError):
                setattr(record, field, "changed")

    @pytest.mark.parametrize("day", [0, 7, True, 1.5, "1"])
    def test_posting_value_date_must_be_in_window(self, day):
        with pytest.raises(InvalidRequestException, match="Day"):
            EntryModel("ACC-001", "AED", Decimal("1.00"), day, "CREDIT", "E1")

    def test_invalid_business_event_remains_representable_for_audit(self):
        event = EventModel("E1", 9, "UNKNOWN", "missing", "USD", 20, "not-money")
        assert event.amount == "not-money"
        assert event.value_date == 20

    @pytest.mark.parametrize("field,value", [
        ("amount", ["1.00"]), ("account_id", {}), ("reference_id", []),
        ("booked_day", True), ("instalments", "3"),
    ])
    def test_event_cannot_contain_mutable_or_wrong_type_fields(self, field, value):
        event = EventModel("E1", 1, "CREDIT", "ACC-001", "AED", 1, "1.00")
        with pytest.raises(InvalidRequestException):
            replace(event, **{field: value})

    def test_invalid_account_and_posting_identity_are_rejected(self):
        with pytest.raises(InvalidRequestException):
            AccountModel(" ", "AED", Decimal("0"))
        with pytest.raises(InvalidRequestException):
            EntryModel("ACC-001", "AED", Decimal("1"), 1, "CREDIT", "")

    def test_error_can_retain_empty_rejected_identifiers(self):
        decision = DecisionModel("", "", "REJECTED", "Missing identifiers", "")
        assert decision.event_id == ""
        with pytest.raises(InvalidRequestException):
            replace(decision, message=[])
        with pytest.raises(InvalidRequestException):
            replace(decision, authorization_id=[])
