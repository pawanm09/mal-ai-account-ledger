from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext

import pytest

from src.externals.clients.ledger_data_client import LedgerDataClient
from src.models.account_model import AccountModel
from src.models.event_model import EventModel
from src.services.ledger_service import LedgerService


@pytest.fixture
def service():
    client = LedgerDataClient([
        AccountModel("ACC-001", "AED", Decimal("250.00")),
        AccountModel("ACC-002", "BHD", Decimal("10.000")),
    ])
    return LedgerService(client)


def authorization(event_id="E3", auth_id="Auth-A", amount="200.00"):
    return EventModel(event_id, 2, "AUTHORIZATION", "ACC-001", "AED", 2,
                      amount, authorization_id=auth_id)


def settlement(event_id="E5", auth_id="Auth-A", amount="185.00"):
    return EventModel(event_id, 4, "SETTLEMENT", "ACC-001", "AED", 4,
                      amount, authorization_id=auth_id)


class TestAuthorizations:
    @pytest.mark.parametrize("amount,status,available", [
        ("250.00", "APPROVED", "0.00"),
        ("250.01", "DECLINED", "250.00"),
        ("200.00", "APPROVED", "50.00"),
    ])
    def test_available_balance_boundary(self, service, amount, status, available):
        result = service.process_event(authorization(amount=amount))
        assert result.status == status
        assert service.get_available_balance("ACC-001", 2) == Decimal(available)
        assert service.ledger_data_client.get_balance("ACC-001", 2) == Decimal("250.00")
        assert service.ledger_data_client.get_entries("ACC-001") == ()
        assert service.get_authorizations("ACC-001")[0].status == status

    def test_multiple_holds_and_no_implicit_expiry(self, service):
        assert service.process_event(authorization()).status == "APPROVED"
        assert service.process_event(authorization("B", "Auth-B", "50.00")).status == "APPROVED"
        assert service.process_event(authorization("C", "Auth-C", "0.01")).status == "DECLINED"
        assert service.get_active_holds("ACC-001") == Decimal("250.00")
        assert service.get_available_balance("ACC-001", 6) == Decimal("0.00")

    def test_settlement_releases_full_hold_and_retains_historical_state(self, service):
        service.process_event(authorization())
        client = service.ledger_data_client
        cutoff = client.last_sequence
        original = service.get_authorizations("ACC-001")
        assert service.process_event(settlement()).status == "SETTLED"
        assert client.get_balance("ACC-001", 4) == Decimal("65.00")
        assert service.get_active_holds("ACC-001") == Decimal("0.00")
        assert service.get_available_balance("ACC-001", 4) == Decimal("65.00")
        assert service.get_authorizations("ACC-001")[0].status == "SETTLED"
        assert service.get_authorizations("ACC-001", cutoff) == original
        assert original[0].status == "APPROVED"
        assert service.get_active_holds("ACC-001", cutoff) == Decimal("200.00")
        assert service.get_available_balance("ACC-001", 2, cutoff) == Decimal("50.00")
        with pytest.raises(FrozenInstanceError):
            original[0].status = "SETTLED"

    @pytest.mark.parametrize("amount", ["0.01", "200.00"])
    def test_final_settlement_accepts_small_or_exact_hold_amount(self, service, amount):
        service.process_event(authorization())
        assert service.process_event(settlement(amount=amount)).status == "SETTLED"
        assert service.get_active_holds("ACC-001") == Decimal("0.00")

    def test_settling_one_hold_leaves_other_hold_active(self, service):
        service.process_event(authorization())
        service.process_event(authorization("B", "Auth-B", "50.00"))
        service.process_event(settlement())
        assert service.get_active_holds("ACC-001") == Decimal("50.00")
        assert service.get_available_balance("ACC-001", 4) == Decimal("15.00")

    @pytest.mark.parametrize("changes", [
        {"authorization_id": "Auth-Z"}, {"authorization_id": None},
        {"authorization_id": ""}, {"amount": "200.01"}, {"amount": "0"},
        {"amount": "-1.00"}, {"amount": "NaN"}, {"amount": "1.001"},
        {"account_id": "ACC-002", "currency": "BHD"},
        {"currency": "BHD"}, {"instalments": 2}, {"reference_id": "E3"},
    ])
    def test_invalid_settlement_keeps_money_and_hold(self, service, changes):
        service.process_event(authorization())
        before = service.get_authorizations("ACC-001")
        result = service.process_event(replace(settlement(), **changes))
        assert result.status == "REJECTED"
        assert result.authorization_id == changes.get("authorization_id", "Auth-A")
        assert service.ledger_data_client.get_entries("ACC-001") == ()
        assert service.ledger_data_client.get_entries("ACC-002") == ()
        assert service.get_authorizations("ACC-001") == before

    @pytest.mark.parametrize("changes", [
        {"authorization_id": None}, {"authorization_id": ""},
        {"amount": "NaN"}, {"amount": "0"}, {"amount": "-1"},
        {"amount": "0.001"}, {"instalments": 2}, {"reference_id": "E1"},
    ])
    def test_invalid_authorization_creates_no_state_or_hold(self, service, changes):
        result = service.process_event(replace(authorization(), **changes))
        assert result.status == "REJECTED"
        assert service.get_authorizations("ACC-001") == ()
        assert service.get_active_holds("ACC-001") == Decimal("0.00")

    def test_unknown_settlement_does_not_create_authorization(self, service):
        assert service.process_event(settlement(auth_id="Auth-Z")).status == "REJECTED"
        assert service.get_authorizations("ACC-001") == ()
        assert service.ledger_data_client.get_balance("ACC-001", 4) == Decimal("250.00")

    def test_declined_authorization_cannot_settle_or_be_reused(self, service):
        assert service.process_event(authorization(amount="300.00")).status == "DECLINED"
        assert service.process_event(settlement()).status == "REJECTED"
        assert service.process_event(authorization("Retry", amount="1.00")).status == "REJECTED"
        assert service.get_authorizations("ACC-001")[0].status == "DECLINED"
        assert service.ledger_data_client.get_entries("ACC-001") == ()

    def test_duplicate_authorization_id_and_event_do_not_reserve_twice(self, service):
        service.process_event(authorization())
        assert service.process_event(authorization()).status == "REJECTED"
        assert service.process_event(authorization("Duplicate", amount="1.00")).status == "REJECTED"
        assert service.get_active_holds("ACC-001") == Decimal("200.00")
        assert len(service.get_authorizations("ACC-001")) == 1

    def test_duplicate_settlement_and_reused_authorization_are_rejected(self, service):
        service.process_event(authorization())
        service.process_event(settlement())
        assert service.process_event(settlement()).status == "REJECTED"
        assert service.process_event(settlement("Second")).status == "REJECTED"
        assert service.process_event(authorization("Reuse")).status == "REJECTED"
        assert len(service.ledger_data_client.get_entries("ACC-001")) == 1
        assert service.get_authorizations("ACC-001")[0].status == "SETTLED"

    def test_authorization_ids_are_scoped_by_account(self, service):
        service.process_event(authorization())
        bhd = EventModel("BHD", 2, "AUTHORIZATION", "ACC-002", "BHD", 2,
                         "10.000", authorization_id="Auth-A")
        assert service.process_event(bhd).status == "APPROVED"
        bhd_settle = EventModel("BS", 4, "SETTLEMENT", "ACC-002", "BHD", 4,
                                "9.999", authorization_id="Auth-A")
        assert service.process_event(bhd_settle).status == "SETTLED"
        assert service.get_active_holds("ACC-001") == Decimal("200.00")
        assert service.get_available_balance("ACC-002", 4) == Decimal("0.001")

    def test_backdated_debit_does_not_revoke_approved_hold(self, service):
        service.process_event(authorization())
        service.process_event(EventModel("D", 3, "DEBIT", "ACC-001", "AED", 1, "300.00"))
        assert service.get_available_balance("ACC-001", 3) == Decimal("-250.00")
        assert service.get_authorizations("ACC-001")[0].status == "APPROVED"
        assert service.process_event(settlement()).status == "SETTLED"
        assert service.ledger_data_client.get_balance("ACC-001", 4) == Decimal("-235.00")

    def test_reversal_does_not_reconsider_declined_authorization(self, service):
        service.process_event(EventModel("D", 5, "DEBIT", "ACC-001", "AED", 2, "620.00"))
        event = replace(authorization(amount="90.00"), booked_day=5, value_date=5)
        assert service.process_event(event).status == "DECLINED"
        service.process_event(EventModel("R", 6, "REVERSAL", "ACC-001", "AED", 2, reference_id="D"))
        assert service.get_authorizations("ACC-001")[0].status == "DECLINED"
        assert service.get_active_holds("ACC-001") == Decimal("0.00")

    def test_late_authorization_cannot_use_an_earlier_positive_balance(self, service):
        service.process_event(EventModel("D", 6, "DEBIT", "ACC-001", "AED", 6, "250.00"))
        assert service.process_event(authorization(amount="0.01")).status == "DECLINED"
        assert service.ledger_data_client.get_balance("ACC-001", 2) == Decimal("250.00")

    def test_settlement_reversal_is_explicitly_unsupported(self, service):
        service.process_event(authorization())
        service.process_event(settlement())
        reverse = EventModel("R", 6, "REVERSAL", "ACC-001", "AED", 4, reference_id="E5")
        assert service.process_event(reverse).status == "REJECTED"
        assert service.get_authorizations("ACC-001")[0].status == "SETTLED"

    def test_zero_cutoff_has_no_holds(self, service):
        service.process_event(authorization())
        assert service.get_authorizations("ACC-001", 0) == ()
        assert service.get_available_balance("ACC-001", 2, 0) == Decimal("250.00")

    def test_hold_calculations_preserve_precision_in_small_decimal_context(self, service):
        with localcontext() as context:
            context.prec = 2
            assert service.process_event(authorization(amount="249.99")).status == "APPROVED"
            assert service.get_available_balance("ACC-001", 2) == Decimal("0.01")
            assert service.process_event(settlement(amount="199.99")).status == "SETTLED"
            assert service.get_available_balance("ACC-001", 4) == Decimal("50.01")
