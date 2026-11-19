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
