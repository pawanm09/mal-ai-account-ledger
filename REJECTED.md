# Acceptance review and rejected approaches

Implementation through Step 5 now verifies the financial scenario and policies.
Distinguish contradictions in arithmetic from decisions under an ambiguous policy.

## Current evidence

- `tests/src/services/test_daily_close_service.py` verifies the pre-fee Day 2
  amount, fee days 2/4/5, retained fees after E9, Auth-A/unknown-settlement outcomes,
  declined Auth-B, exact daily-accrual sums, and final AED/BHD balances.
- `tests/src/services/test_authorizations.py` separately verifies approved,
  unsettled holds because Auth-B is declined in the supplied scenario.
- `tests/src/services/test_ledger_service.py` verifies the three conserving BHD
  instalments and immutable reversal behavior.
- The rounded-accrual test uses AED 12.50: each daily 0.005 accrual rounds to 0.01,
  totaling 0.06; rounding the unrounded six-day sum would instead give 0.03.

## All eight acceptance criteria

### 1. Day 2 balance at end of Day 5 before fees is AED -370.00

**Accept.** With E7 known: 1,200.00 - 950.00 - 620.00 = -370.00.
Auth-A is a hold, not a ledger debit. This explicitly excludes fee postings.

### 2. E7 causes exactly one fee, on Day 2

**Reject under the selected retrospective assessment policy.** Before fees,
the corrected balances on Days 2–5 are -370.00, 30.00, -155.00, -155.00.
Chronological assessment, including prior fees, gives:

| Assessment day | Balance before that day's fee | New fee | Balance after fee |
|---|---:|---:|---:|
| 2 | -370.00 | 25.00 | -395.00 |
| 3 | 5.00 | 0.00 | 5.00 |
| 4 | -180.00 | 25.00 | -205.00 |
| 5 | -205.00 | 25.00 | -230.00 |

Days 2 and 4 are reassessed after E7; Day 5 closes before E9. Total fees are
AED 75.00. The historical assessment-day interpretation is documented in
`AMBIGUITIES.md`; the brief does not precisely specify late-assessment timing.

### 3. Auth-A's Day 4 settlement must be accepted

**Accept for the supplied stream.** Its AED 200 hold was approved; settlement is
AED 185. Debit 185 and release the entire hold under final-settlement semantics.
E7 arriving later cannot change the original settlement decision.

### 4. Unknown authorization settlements must be rejected without a debit

**Accept under the author's chosen policy.** E6 records an error and no financial
posting. Rejecting unknown references is defensible here; forced settlements are
a possible alternative policy, not a requirement stated by the non-negotiable rules.

### 5. An approved Auth-B reduces available balance, not ledger balance

**Accept.** Holds reserve availability only. Auth-B is actually declined in this
stream. A separate approved-unsettled-hold test will verify the conditional claim.

### 6. E9 restores all balances and fees to their pre-E7 values

**Reject under the retained-fee policy.** Reversing AED 620 of principal does not
refund AED 75 in fees. ACC-001's pre-interest balance becomes AED 390 rather than
AED 465. Fee entries and original decisions remain auditable. Append-only does
not forbid refunds; automatic fee refunds simply are not the selected policy.

### 7. Each BHD instalment must be 3.334

**Reject: arithmetic contradiction.** Three times 3.334 is 10.002, not 10.000.
Allocate 3.334, 3.333, and 3.333 to conserve the supplied amount at BHD precision.

### 8. Discard any interest reconciliation remainder

**Reject: contradicts exact reconciliation.** Capitalize the sum of already-rounded
daily accruals. Do not independently round an unrounded aggregate and discard a
difference. The chosen policy yields AED 0.93 and BHD 0.008 in this stream.

## Design alternatives considered before implementation

- Sorting inputs by booked day: violates explicit arrival order, especially E10.
- Accepting forced settlement E6 with a warning: author chose rejection instead.
- Automatically refunding fees after E9: author chose principal-only reversal.
- Separate ReplayService class: ordinary functions in main.py replace the proposed
  orchestration class and reduce indirection for this small exercise.
- BHD missing-fee test as the deliberate failure: primarily exposes missing pricing
  information. The planned partial-settlement failure better exposes our lifecycle.
- Floating-point money or independently rounding three equal instalments: risks
  monetary error and violates exact conservation.

These were design discussions, not code that was built and subsequently removed.

## Approaches abandoned during implementation

None so far. Update this section with actual evidence if an implementation approach
is tried and abandoned. Do not invent a false start to satisfy the deliverable.
