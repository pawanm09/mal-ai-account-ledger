# In-memory account ledger

A six-day, Python 3 account-ledger assessment. No web layer, persistence, UI,
database, or external service calls. Financial state will live only in memory.

## Current status

Step 1: package skeleton and design documentation. Ledger behavior, replay output,
and tests are not implemented yet. `main.py` and `src/container.py` currently
contain module descriptions only; running `main.py` does not exercise a ledger.

## Setup

Use Python 3.11 or newer. The verified interpreter version will be recorded in
`WORKLOG.md`. Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m pytest --version
python3 -c "import main, src.container, src.models, src.services, src.exceptions, src.externals.clients, tests.src.models, tests.src.services, tests.src.externals.clients, tests.design_limitations; print('Package imports OK')"
```

There are no tests in Step 1. Pytest's `no tests collected` result is not a passing
correctness suite. Behavioral tests will arrive with their implementation steps.

## Structure

The layout follows `/Users/pawan.mishra/Downloads/pendency-system-design-main`:

```text
main.py                         supplied events, replay, and output (Step 6)
src/container.py                explicit dependency construction
src/models/                    immutable records and exact-money helpers
src/exceptions/                domain validation exception
src/externals/clients/         in-memory append/query storage
src/services/                 ledger operations and daily closing
tests/src/                    tests mirroring the source packages
tests/test_replay.py           whole-stream test (Step 6)
tests/design_limitations/      deliberate failing test (Step 7)
```

`externals/clients` matches the reference name; it will contain an in-memory
client, not a network integration. There will be two services, `LedgerService`
and `DailyCloseService`, wired by constructors. Ordinary functions in `main.py`
will coordinate the replay. Tests will use real in-memory clients.

## Required accounts and rules

- ACC-001: AED, opening balance 0.00; ACC-002: BHD, opening balance 0.000.
- Ledger balance on a day includes postings with `value_date <= day`, limited
  to the records known at the requested recording cutoff.
- Overdraft fee: AED 25.00, at most once per account/day with a negative closing
  ledger balance. The fee's value date is its assessment day.
- Daily interest: 0.04% on positive closing ledger balances only. Round daily
  to the currency precision; capitalize their exact sum as one credit per
  account at the end of Day 6.
- AED has two decimal places; BHD has three. Use exact decimal arithmetic.
- No event record is mutated or deleted. Reversals append compensating postings.
- Authorize only when ledger balance minus existing holds minus the new hold
  is at least zero. Holds do not change the ledger balance.

Timing interpretations and unsupported cases are explicit in `AMBIGUITIES.md`.

## Supplied input, in arrival order

| ID | Booked day | Operation | Account | Amount / reference | Value day |
|---|---:|---|---|---|---:|
| E1 | 1 | CREDIT | ACC-001 | AED 1,200.00 | 1 |
| E2 | 1 | DEBIT | ACC-001 | AED 950.00 | 1 |
| E3 | 2 | AUTHORIZATION | ACC-001 | Auth-A, AED 200.00 | 2 |
| E4 | 3 | CREDIT | ACC-001 | AED 400.00 | 3 |
| E5 | 4 | SETTLEMENT | ACC-001 | Auth-A, AED 185.00 | 4 |
| E6 | 4 | SETTLEMENT | ACC-001 | Auth-Z, AED 180.00 | 4 |
| E7 | 5 | DEBIT | ACC-001 | AED 620.00 | 2 |
| E8 | 5 | AUTHORIZATION | ACC-001 | Auth-B, AED 90.00 | 5 |
| E9 | 6 | REVERSAL | ACC-001 | Reverse E7 | 2 |
| E10 | 5 | CREDIT | ACC-002 | BHD 10.000 in three instalments | 5 |

E10 remains after E9. The processing clock does not move backward.

## Planned commands and output (available after Steps 6 and 7)

```bash
python3 main.py
python3 -m pytest tests/src tests/test_replay.py
python3 -m pytest tests/design_limitations
python3 -m pytest
```

The first test command will run the passing correctness suite. The limitation
command will intentionally fail; the full suite will include that failure too.
The failure and its meaning will be annotated in the test and documented here.

Replay output will show each day's account balances, fees, authorization states,
holds, available balance, errors, and interest. Reports will label their recording
cutoff and distinguish original snapshots from historical corrections and final
restated balances. No silent replacement of earlier reports.

## Expected results, not yet implementation-verified

Under the policies chosen in `AMBIGUITIES.md`:

| Day | Final restated ACC-001 balance before capitalization | Daily interest |
|---|---:|---:|
| 1 | AED 250.00 | AED 0.10 |
| 2 | AED 225.00 | AED 0.09 |
| 3 | AED 625.00 | AED 0.25 |
| 4 | AED 415.00 | AED 0.17 |
| 5 | AED 390.00 | AED 0.16 |
| 6 | AED 390.00 | AED 0.16 |

- After E7, before fees, the restated Day 2 balance is AED -370.00.
- Fees: AED 25.00 for each of Days 2, 4, and 5, totaling AED 75.00.
- ACC-001 interest: AED 0.93; final Day 6 balance: AED 390.93.
- ACC-002 instalments: BHD 3.334, 3.333, 3.333; daily interest on Days 5 and 6:
  BHD 0.004 each; final Day 6 balance: BHD 10.008.
- Auth-A settles, Auth-Z's settlement is rejected, Auth-B is declined.

## Delivery checkpoints

1. Skeleton, requirements, policies, and setup verification.
2. Exact money, immutable models, and append-only storage.
3. Credits, debits, instalments, and reversals.
4. Authorizations and settlements.
5. Daily closing, historical fees, and interest.
6. Supplied replay, readable daily output, and end-to-end verification.
7. Deliberate failing test and completed assessment documentation.

After every step, the author reviews the code, runs checks, and makes a real
local commit before the next step. Preserve history without squashing. AI
assistance is disclosed in `WORKLOG.md`; no history or timestamps are fabricated.
