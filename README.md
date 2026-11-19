# In-memory account ledger

A six-day, Python 3 account-ledger assessment. No web layer, persistence, UI,
database, or external service calls. Financial state will live only in memory.

## Current status

Step 6: the complete supplied replay and daily reporting run with `python3 main.py`.
All 178 correctness tests pass, including a subprocess test of that command.
The deliberate failing test and final documentation review remain for Step 7.

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

Run the currently implemented behavioral tests:

```bash
python3 -m pytest tests/src tests/test_replay.py -q
```

These tests cover exact money, immutable records, independent account balances,
recording cutoffs, batch validation, transaction acceptance/rejection, duplicate
attempts, instalment conservation, reversals, holds, fees, interest, and finalization.
Replay tests verify arrival order, financial totals, all daily output fields,
original-versus-corrected views, and repeatability with isolated in-memory state.

## Structure

The layout follows `/Users/pawan.mishra/Downloads/pendency-system-design-main`:

```text
main.py                         supplied events, replay, and output
src/container.py                explicit dependency construction
src/models/                    immutable records and exact-money helpers
src/exceptions/                domain validation exception
src/externals/clients/         in-memory append/query storage
src/services/                 ledger operations and daily closing
tests/src/                    tests mirroring the source packages
tests/test_replay.py           whole-stream and runnable-script tests
tests/design_limitations/      deliberate failing test (Step 7)
```

`externals/clients` matches the reference name; it will contain an in-memory
client, not a network integration. There will be two services, `LedgerService`
and `DailyCloseService`, wired by constructors. Ordinary functions in `main.py`
will coordinate the replay. Tests will use real in-memory clients.

### Implemented storage model

```text
EventModel    (original input attempt) --+
EntryModel    (signed money posting) ---+--> JournalRecord(sequence, payload)
DecisionModel (outcome or error) -------+         |
                                                v
                                     private append-only list
                                                |
                                                v
                                       tuple query snapshots
```

Account records hold immutable opening balances. Each journal append gets a
sequence, including errors and decisions. A cutoff is an inclusive **journal
sequence**, not an event number or booked day. Cutoff zero includes opening
balances only. Balance queries include only financial postings whose value date
is on or before the requested day and whose sequence is within the cutoff.

`append_entries` validates the complete batch before writing any postings. The
data client validates storage invariants, not business authorization or duplicate
effects; those checks belong to the service. It intentionally retains
duplicate input attempts for audit. Public snapshots cannot mutate storage; the
private Python attributes are not a security boundary against hostile callers.

### Implemented transaction flow

`LedgerService.process_event` records each input attempt, validates it, builds
the entire posting batch, appends that batch, and records an ACCEPTED decision
(SETTLED for a successful settlement). Authorizations append an APPROVED or
DECLINED decision without financial postings.
Domain validation failures instead append a REJECTED decision with no postings.
Unexpected programming errors propagate rather than being hidden as rejections.

Credits may allocate instalments; debits may overdraw. A reversal derives the
full amount from the referenced credit/debit postings and appends one opposite
posting linked by `reference_event_id`. Original records and decisions remain.
Duplicate IDs (including previously rejected IDs) and repeated reversals are
rejected. The service supports CREDIT, DEBIT, REVERSAL, AUTHORIZATION, and SETTLEMENT.

### Authorization lifecycle

```text
New valid authorization request
    +-- enough available balance --> APPROVED (active hold)
    |                                   |
    |                                   +-- final settlement --> SETTLED (no hold)
    +-- insufficient balance ------> DECLINED (no hold)

Malformed / duplicate requests --> REJECTED audit decision; no state change
```

`get_authorizations` rebuilds immutable snapshots from input and decision records.
`get_active_holds` sums only APPROVED amounts. `get_available_balance` subtracts
those holds from the ledger balance at the requested day and journal cutoff.
To reproduce a historical view, supply both its day and its original cutoff;
omitting the cutoff intentionally uses all currently known decisions.

Auth-A's AED 185 settlement releases the full AED 200 hold, leaving no implicit
AED 15 hold. Unknown, declined, already-settled, or over-limit settlements are
rejected. Approved holds do not expire automatically. Backdated postings do not
rewrite past approvals or declines. Partial captures remain a documented design
limitation; the explicit failing demonstration will be added in Step 7.

### Daily processing and finalization

Use `DailyCloseService.process_event` for chronological replay. It coordinates:

```text
Arrival -> close preceding days -> LedgerService.process_event
                                        |
                                        +-> accepted posting: reassess closed days

End of input -> close Day 6 -> sum rounded daily accruals
                                  -> interest credits -> FINALIZED marker
```

`close_through(day)` and `reconcile()` assess fees chronologically, including
earlier fees in later balances. Fees are identified by account and effective day
and never refunded automatically. DAY_CLOSED markers and FINALIZED are append-only
records; reconstructing services over the same journal preserves idempotence.
The current day is not assessed after every input, avoiding intraday fees.

`daily_accruals` returns six provisional daily amounts at a recording cutoff;
before finalization this includes a projection for days not yet closed. The final
calculation includes all input and fees but excludes INTEREST postings, avoiding
self-interest after capitalization. `finalize()` returns True on success, including
a repeated call, and False if a fee policy is missing. In the latter case the
journal contains FEE_ERROR records and corrections can still be submitted.

After FINALIZED, attempts submitted through either service are recorded and
rejected without financial effects. Direct data-client methods are internal
storage primitives, not an alternative business entry point.

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

## Run the replay and correctness suite

```bash
python3 main.py
python3 -m pytest tests/src tests/test_replay.py
```

The deliberate failure will be added in Step 7. Its separate command will be
`python3 -m pytest tests/design_limitations`; default full discovery will include
it as well. At Step 6 there is no deliberately failing test yet.

### Read the output

- `ARRIVAL`: each supplied event's booked day, value date, and decision. E10
  appears after E9. The runner uses a fresh ledger on every invocation.
- `ORIGINAL CLOSE`: reconstructs the snapshot at the DAY_CLOSED journal marker,
  before any later arrival changes historical balances. Day 6's original close
  is explicitly the pre-capitalization snapshot; the final row includes interest.
- `CORRECTION AFTER E7/E9/E10`: shows affected already-closed days at the new
  recording cutoff. No original snapshot is overwritten.
- `FINAL RESTATED`: all six value-dated closing balances at the final cutoff.
  Holds and authorization states are as known at that cutoff, not a claim that
  those states existed on the earlier value day. Use ORIGINAL CLOSE for the
  original authorization state; for example, Auth-A was APPROVED on Day 2.
- `Fees assessed this day`: fees effective on the row's day, with the sequence
  at which they were recorded. A retained fee can appear on a now-positive day.
- `Errors booked/assessed this day`: rejected/declined requests grouped by booked
  day; fee-policy errors grouped by assessment day. Each includes its recording
  sequence. `none` is printed when no error exists, including for ACC-002 here.
- `Rounded daily interest`: calculated from the balance excluding capitalization.
  Original and correction reports are provisional; final reports reconcile to
  the posted interest credits.
- `WINDOW TOTALS`: assessed fee total, actual capitalized amount, and final balance
  for each account, always formatted to its currency precision.

Each day view prints both accounts. Journal sequence counts include inputs,
postings, decisions, and control markers; they are not input event numbers.

## Verified financial results (core tests and runnable replay)

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
