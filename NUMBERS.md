# Numbers and constants

Initial design inventory. Add implementation constants as they are introduced.
Supplied requirements are not tuning parameters. Expected results are derived
values to assert in tests, not constants to hard-code in financial calculations.

## Supplied numbers

| Constant | Meaning | Why this value, not half? |
|---|---|---|
| Days 1 through 6 | Assessment window | Required; three days would omit settlement, backdating, reversal, and capitalization. |
| Opening 0.00 AED / 0.000 BHD | Account starting balances | Required; half of zero is still zero. Currency scale must remain explicit. |
| AED 25.00 | Daily overdraft fee | Required; AED 12.50 changes the contract and balance results. |
| One fee per account/day | Assessment limit | Required; a fractional occurrence is meaningless, and retries must not charge again. |
| 0.04% = 0.0004 | Daily interest rate | Required; 0.0002 halves the promised interest rate. This is daily, not annual. |
| Two AED decimal places | AED minor-unit precision | Required; one decimal place loses fils precision. |
| Three BHD decimal places | BHD minor-unit precision | Required; precision is an integer and fewer places lose minor units. |
| Three instalments | E10 allocation count | Required; the count cannot be halved into a fractional posting count. |
| Zero | Authorization lower bound and interest sign boundary | Required; authorize at exactly zero, accrue interest only above zero. |

### Input amounts

| Event | Amount | Why not half? |
|---|---|---|
| E1 | AED 1,200.00 | Supplied credit; halving alters available funds. |
| E2 | AED 950.00 | Supplied debit; halving changes all subsequent balances. |
| E3 | AED 200.00 | Supplied hold; halving changes reserved funds and settlement comparison. |
| E4 | AED 400.00 | Supplied credit; halving changes historical overdraft behavior. |
| E5 | AED 185.00 | Supplied settlement; halving changes the debit and unused hold release. |
| E6 | AED 180.00 | Supplied rejected-settlement attempt; preserve its original requested amount. |
| E7 | AED 620.00 | Supplied backdated debit; halving changes which days are negative. |
| E8 | AED 90.00 | Supplied hold request; preserve the request even when declined. |
| E9 | Amount derived from E7 | Full reversal; halving would be a partial reversal, a different operation. |
| E10 | BHD 10.000 | Supplied total; halving violates the event. |

Input booked days, value days, order, and identifiers are copied unchanged from
the table in `README.md`. They identify the scenario, not configurable thresholds.

## Chosen numbers and conventions

| Choice | Reason and half-value comparison |
|---|---|
| Python 3.11 minimum | Available interpreter is 3.11.5; a modern standard-library baseline. Version numbers are compatibility labels, not divisible quantities. No claim that older Python is inherently incapable of the task. |
| pytest 8.3.5 | Known stable pytest release compatible with Python 3.11, pinned for repeatable setup. No runtime dependency is needed. Halving a release number does not define a meaningful dependency policy. |
| Decimal quanta 0.01 AED / 0.001 BHD | Derived from required scales. Half a quantum is not a representable stored currency unit. |
| ROUND_HALF_UP | Explicit, familiar tie rule; exact half units round away from zero. The brief does not prescribe it. ROUND_HALF_EVEN is a valid alternative but must not be mixed into this design. |
| One minor unit per remainder allocation | Allocate indivisible units to the earliest instalments. Half a minor unit cannot be stored. |
| One-based monotonically increasing recording sequence | Deterministic arrival cutoffs, independent of wall-clock time. Sequence magnitude has no monetary meaning. |
| One final settlement per authorization | Small lifecycle matching the supplied stream. Multiple partial captures are a documented limitation, not silently approximated. |
| One final capitalization per account | Matches a single end-of-window credit per currency account; halving an operation count is meaningless. No posting is needed for a zero total. |
| Cutoff zero | Query opening balances before any journal records. Negative cutoffs are invalid; this is an identity boundary, not a tunable constant. |
| Quantization precision: integer digits + currency scale + one carry digit | Derived per calculation rather than relying on Decimal's default significant-digit limit. The extra digit permits 99.999 to become 100.00. Halving precision can lose money or raise an arithmetic error. |
| Sum precision: largest integer width + scale + digits in count | Derived headroom for summing the batch without dropping minor units. At least one integer digit handles zero and fractional amounts. Halving headroom can silently round large totals. |

The money helpers use local Decimal contexts, preserving the caller's context.
Precision is calculated from the operands; no arbitrary monetary maximum has
been introduced. Python Decimal's implementation limits on exponent and available
memory still apply; this is not an unlimited-resource arithmetic service.

No arbitrary tolerances, interest remainders, FX rates, BHD fee amounts, hold
timeouts, retry counts, or performance targets are introduced. If a later step
needs another numeric bound or arithmetic setting, document it here before use.
