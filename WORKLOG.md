# Worklog

Times are actual UTC observations from the execution environment. Entries record
work performed, not manufactured duration estimates. Earlier planning happened in
conversation; no precise start/end timestamps for it were captured here.

The author uses AI assistance (OpenCode) for design, implementation, and checks.
The author will independently review code, run checks, and make each incremental
Git commit. AI-generated code is not evidence that the author has reviewed it.

## Step 1: skeleton and requirements

### 2026-11-19T07:21:58Z — Implementation start

- Confirmed destination `/Users/pawan.mishra/Documents/Personal/mal-ai` was empty.
- Environment reports Python 3.11.5 and pip 23.2.1.
- Prior conversation inspected the reference repository's services, container,
  models, in-memory clients, exceptions, and pytest layout.
- Author requested step-by-step execution, stopping for their review and commit.
- Creating package skeleton, pinned test dependency, and five required documents.
- Selected policies carried forward: reject unknown settlement, retain fees after
  reversal, chronological historical assessment, exact rounding, final settlement.
- No runtime behavior or behavioral tests are claimed complete at this checkpoint.

### 2026-11-19T07:51:31Z — Step 1 verification complete

- Created the reference-style package skeleton and all five required documents.
- Documented all ten inputs, all eight criteria, policy-dependent rejections,
  expected totals, and 19 ambiguity resolutions. Expected totals remain design
  calculations, not outputs verified against an implemented ledger.
- Created an isolated `.venv` and installed `pytest==8.3.5` successfully using
  `.venv/bin/python -m pip install -r requirements.txt`.
- `.venv/bin/python -m pip check`: no broken requirements.
- `.venv/bin/python -m pytest --version`: pytest 8.3.5.
- Imported main, container, source packages, and test packages: all succeeded.
- `.venv/bin/python -m pytest --collect-only -q`: no tests collected, as expected
  for the skeleton. This is not a passing correctness-suite result.
- Pytest's transitive dependencies resolved to iniconfig 2.3.1, packaging 26.3,
  and pluggy 1.7.0. Only the direct test dependency is pinned at this stage.
- No implementation approach was built and abandoned. No Git initialization or
  commits were performed. Step 2 awaits the author's review and commit confirmation.

## Step 2: exact money and append-only storage

### 2026-11-19T08:05:56Z — Implementation start

- Author confirmed Step 1 was committed; verified commit `1777c40`.
- Git showed an untracked `.idea/` directory. Treated it as the author's IDE
  configuration and left it untouched.
- Started immutable account/input/posting/decision records, exact-money helpers,
  and the in-memory append/query client with mirrored behavioral tests.
- Kept raw input business validation distinct from validated postings so future
  service rejections can retain the original input attempt.

### 2026-11-19T08:08:35Z — Code verification checkpoint

- Implemented currency parsing, explicit rounding, fixed-scale formatting,
  positive-transaction checks, and exact summation with operand-derived precision.
- Implemented frozen records and tuple snapshots; batch validation occurs before
  any financial append. Events and decisions never enter balance calculations.
- Added one shared validation module for identifiers and six-day bounds instead
  of repeating these checks across models and queries.
- `.venv/bin/python -m pytest tests/src -q`: 64 passed in 0.09 seconds.
- Tests include AED/BHD ties, non-finite inputs, large totals under a deliberately
  small caller Decimal precision, duplicate audit attempts, invalid batches,
  immutable snapshots, and Day 2 balances before/after a backdated posting.
- `git diff --check`: passed for tracked changes at this checkpoint; new source
  files were still untracked. `.venv/bin/python -m pip check`: no broken requirements.
- Updating README, NUMBERS, and AMBIGUITIES to describe implemented behavior.
- No commits performed. Step 3 awaits the author's review and commit confirmation.

## Step 3: credits, debits, instalments, and reversals

### 2026-11-19T08:13:48Z — Implementation start

- Author confirmed Step 2 committed; verified commit `1538e3e`.
- `.idea/` remains untracked user configuration; left untouched.
- Implementing the first business operations against the real in-memory client.

### 2026-11-19T08:14:59Z — Code verification checkpoint

- Added LedgerService.process_event with audit-first input recording, validation,
  complete-batch posting, and explicit accepted/rejected outcomes.
- Added integer-minor-unit instalment allocation without floating point or
  independently rounded thirds. E10 produces 3.334, 3.333, and 3.333 BHD.
- Added reference_event_id to postings for linked full reversals. Original
  postings and snapshots stay unchanged. Full instalment reversals aggregate
  the original children into one exact opposite posting.
- Duplicate IDs, rejected-ID retries, invalid amounts/dates, wrong-account
  references, repeated reversals, and unsupported kinds produce no money movement.
- Used Decimal.copy_negate rather than unary negation to preserve exact large
  amounts even when the caller uses a small Decimal context precision.
- `.venv/bin/python -m pytest tests/src -q`: 112 passed in 0.33 seconds.
- `git diff --check`: passed for tracked changes at this checkpoint.
- Updating policy documentation for minimum-size instalments, original-date full
  reversal, and ordinary debits being allowed to overdraw.
- No code approach was abandoned during this step. No commits performed.

## Step 4: authorizations and settlements

### 2026-11-19T08:30:18Z — Implementation start

- Author confirmed Step 3 committed; verified commit `2ba335a`.
- `.idea/` remains the only untracked user directory from before this step.
- Extending LedgerService with journal-derived authorization states, active holds,
  available balances, and final settlement validation.

### 2026-11-19T08:31:41Z — Code verification checkpoint

- Added immutable AuthorizationModel snapshots rebuilt from original input and
  outcome records. No original authorization event or decision is mutated.
- APPROVED holds reserve money; DECLINED requests do not. Successful final
  settlements append a debit plus SETTLED decision, releasing the whole hold.
- Unknown, declined, duplicate, wrong-account, and over-limit settlements reject
  without money movement. Failed attempts retain their authorization reference.
- Availability uses the latest valid booked day seen, so late authorizations
  cannot bypass later debits by using an earlier positive ledger balance.
- Added tests for exact-zero boundary, one-minor-unit excess, multiple holds,
  account-scoped IDs, no expiry, historical cutoff state, post-approval overdraft,
  immutable decisions after reversal, duplicate outcomes, and BHD precision.
- `.venv/bin/python -m pytest tests/src -q`: 151 passed in 0.16 seconds.
- `git diff --check`: passed for tracked changes at this checkpoint.
- Updated README and AMBIGUITIES with implemented lifecycle and ID reuse policy.
- No implementation approach abandoned, no commits performed. Step 5 awaits
  the author's review and commit confirmation.

## Step 5: daily closing, fees, and interest

### 2026-11-19T08:52:08Z — Implementation start

- Author confirmed Step 4 committed; verified commit `6caaf70`.
- `.idea/` remains untracked user configuration and is untouched.
- Implementing explicit day close, chronological historical assessment, exact
  daily accruals, once-only capitalization, and post-finalization rejection.

### 2026-11-19T08:53:41Z — Code verification checkpoint

- Added DailyCloseService with coordinated event processing, close/reconcile,
  provisional accrual queries, and finalization.
- Added immutable DAY_CLOSED and FINALIZED journal markers. Reconstructed service
  instances preserve fee and interest idempotence without separate mutable flags.
- Added unsupported-BHD-fee errors that block finalization but permit correcting
  input; repeated checks do not duplicate the same account/day error.
- Tests exercise E1–E10 in supplied order, including E10 after E9: fees AED 75.00,
  final balances AED 390.93 and BHD 10.008, exact rounded interest capitalization.
- Tested intraday overdrafts, zero closes, fee carry-forward, no interest on
  nonpositive balances, no hold deduction from interest base, no self-interest,
  reconstruction/retry idempotence, historical cutoff projections, and late input.
- `.venv/bin/python -m pytest tests/src -q`: 172 passed in 0.18 seconds.
- `git diff --check`: passed for tracked changes at this checkpoint.
- Updated policy docs and rejection evidence to distinguish verified financial
  tests from the still-pending runnable reporting script.
- No implementation approach abandoned and no commits performed. Step 6 awaits
  the author's review and commit confirmation.
