from decimal import Decimal, localcontext

import pytest

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.models.money import (
    currency_quantum,
    format_amount,
    parse_amount,
    round_amount,
    split_amount,
    total_amounts,
    transaction_amount,
)


class TestMoney:
    @pytest.mark.parametrize("currency,value,expected", [
        ("AED", "12.3", "12.30"),
        ("BHD", "12.3", "12.300"),
        ("AED", "12.3000", "12.30"),
        ("BHD", "0.001", "0.001"),
        ("AED", "-0.00", "0.00"),
    ])
    def test_amount_is_stored_at_currency_precision(self, currency, value, expected):
        assert str(parse_amount(value, currency)) == expected
        assert format_amount(value, currency) == f"{currency} {expected}"

    @pytest.mark.parametrize("currency,value,expected", [
        ("AED", "1.005", "1.01"),
        ("AED", "-1.005", "-1.01"),
        ("AED", "1.0049", "1.00"),
        ("BHD", "1.0005", "1.001"),
        ("BHD", "-1.0005", "-1.001"),
        ("BHD", "0.0040", "0.004"),
        ("AED", "99.999", "100.00"),
    ])
    def test_calculated_amount_rounding(self, currency, value, expected):
        assert str(round_amount(value, currency)) == expected

    @pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "bad", "", 1.2, 1, True, None])
    def test_invalid_money_is_rejected(self, value):
        with pytest.raises(InvalidRequestException):
            parse_amount(value, "AED")

    @pytest.mark.parametrize("currency,value", [("AED", "1.001"), ("BHD", "1.0001")])
    def test_transaction_input_is_not_silently_rounded(self, currency, value):
        with pytest.raises(InvalidRequestException, match="precision"):
            parse_amount(value, currency)

    @pytest.mark.parametrize("value", ["0", "-0.00", "-1.00"])
    def test_transaction_requires_positive_amount(self, value):
        with pytest.raises(InvalidRequestException, match="positive"):
            transaction_amount(value, "AED")

    def test_smallest_transaction_is_allowed(self):
        assert transaction_amount("0.001", "BHD") == Decimal("0.001")

    def test_unknown_currency_is_rejected(self):
        with pytest.raises(InvalidRequestException, match="currency"):
            currency_quantum("USD")

    def test_empty_total_keeps_currency_scale(self):
        assert str(total_amounts([], "BHD")) == "0.000"

    def test_summing_large_balances_keeps_every_minor_unit(self):
        amounts = [Decimal("9999999999999999999999999999.99"), Decimal("0.01")]
        with localcontext() as context:
            context.prec = 3
            assert str(total_amounts(amounts, "AED")) == "10000000000000000000000000000.00"
            assert str(round_amount("999.995", "AED")) == "1000.00"
            assert context.prec == 3

    def test_sum_conserves_bhd_instalments_and_signed_postings(self):
        values = [Decimal("3.334"), Decimal("3.333"), Decimal("3.333")]
        assert str(total_amounts(values, "BHD")) == "10.000"
        assert str(total_amounts([Decimal("1.00"), Decimal("-1.00")], "AED")) == "0.00"

    @pytest.mark.parametrize("value,currency,count,expected", [
        ("10.000", "BHD", 3, ("3.334", "3.333", "3.333")),
        ("0.05", "AED", 3, ("0.02", "0.02", "0.01")),
        ("1.00", "AED", 2, ("0.50", "0.50")),
        ("0.001", "BHD", 1, ("0.001",)),
        ("0.03", "AED", 3, ("0.01", "0.01", "0.01")),
    ])
    def test_instalment_allocation(self, value, currency, count, expected):
        with localcontext() as context:
            context.prec = 2
            parts = split_amount(value, currency, count)
            assert tuple(str(part) for part in parts) == expected
            assert total_amounts(parts, currency) == Decimal(value)

    @pytest.mark.parametrize("count", [0, -1, True, 1.5, "3", 101])
    def test_invalid_instalment_count(self, count):
        with pytest.raises(InvalidRequestException):
            split_amount("1.00", "AED", count)
