# Ambiguities and selected policies

These are explicit interpretations, not claims that the brief mandates every
choice. Policies apply to the bounded, single-threaded, six-day exercise.

## 1. Arrival order versus booked day versus value date

Keep E1 through E10 in the supplied order. Booked day is input metadata; value
date determines financial effectiveness; recording sequence determines what was
known. E10 arrives after E9 despite its Day 5 booked date. Sorting by booked day
would change the stated replay order, so it is rejected.

## 2. Daily close boundaries

The processing day only moves forward. Before a later booked-day event, close
intervening days. Backdated postings immediately trigger reassessment of affected
already-closed days. The current day gets a fee only at its close, avoiding fees
on temporary intraday overdrafts. At end of input, close through Day 6.

For this stream: close Day 4 before E7; after E7 reassess Days 2–4; close Day 5
before E9; process E10 while the processing day remains 6; finalize afterward.

Step 5 implementation: DailyCloseService.process_event is the coordinated replay
entry point. LedgerService.process_event handles individual operations; calling
it alone does not close days. Explicit close markers also advance the processing
day used for authorization. Reconciliation scans all closed days (at most six)
instead of maintaining a potentially stale affected-day cache. Closed-day markers
preserve original boundaries while later reassessment can append fees or errors.

## 3. Historical fee assessment and dating

The phrase "day assessed" does not explicitly define late discovery. Interpret
it as the historical day being assessed. A fee discovered after E7 can have
assessment day/value date 2 and a later recording sequence. Record both. The
alternative, assessing only on discovery day, produces different numbers.

The chosen retrospective interpretation yields fees on Days 2, 4, and 5. This
assumption is central to rejecting criterion 2 and must be defended explicitly.

## 4. Fee ordering and idempotence

Assess affected closed days in chronological order. Determine eligibility before
that day's new fee, including all earlier booked fee postings. Assess once per
account/effective day, even when close or reconciliation is called again. Later
days include earlier fees. Do not iterate a new fee into another fee on the same
day.

## 5. Reversal and fee refunds

E9 appends an opposite posting for E7 with value date 2. Fees are retained because
no automatic refund policy is supplied, as explicitly selected by the author.
Append-only alone does not imply this policy: compensating fee refunds would
also be append-only. A later refund feature would require an explicit operation.

## 6. Settlement without an authorization

Reject E6 and record an error; no funds leave the account. This is the author's
selected policy and accepts criterion 4. Some payment systems accept forced
settlements, but that behavior is not a non-negotiable requirement here.

## 7. Settlement completeness and amount

Treat a settlement as final. It debits the settlement amount and releases the
entire active hold. Auth-A's AED 185 settlement releases AED 200, including the
unused AED 15. Partial captures are unsupported. For this bounded design, reject
settlements exceeding the approved hold rather than inventing an additional
authorization rule. An approved hold is not re-decided using later knowledge.

## 8. Hold dates, expiration, and declined decisions

Holds affect availability when processed and remain active until settled; no
expiry is inferred from the six-day window. Declined holds never reserve money.
E9 does not retroactively approve Auth-B. The authorization availability query
uses the current processing day and current known entries, not a historical
value date to bypass a current lack of funds.

Step 4 detail: an authorization ID is reserved for its account once it receives
an APPROVED or DECLINED decision and cannot be reused after settlement or decline.
A malformed/rejected authorization creates no lifecycle state; a corrected
request may use the same authorization ID with a new event ID. The original
event ID remains reserved. Unknown settlement errors do not create an authorization.

Until explicit close coordination is introduced, the latest valid booked day in
the input journal establishes the authorization processing day. Out-of-window
days do not advance it; a rejected request with a valid booked day does. Late
arrivals never move the processing day backward. Day-plus-cutoff queries are
historical views; a past day queried without a cutoff uses today's known holds.

Settlement does not recheck current available funds for an already-approved hold.
It may therefore post after unrelated debits make the account negative. It must
still be positive, not exceed the original hold, and reference an active approval
on the same account. Backdated settlement value dates are permitted by the common
date rules; the hold is released only when the settlement is recorded, never
retroactively. Reversing a settlement lifecycle is explicitly unsupported.

## 9. Interest correction and storage

Daily accruals are derived, rounded calculations, not spendable postings. Recompute
affected daily accruals using corrected historical ledger balances, including
retained fees. Historical reports keep their cutoff labels; source records are
never rewritten. Only the final total becomes a ledger credit.

## 10. Day 6 interest and capitalization

Process every supplied arrival before finalizing. Compute Day 6 accrual before
capitalization, so capitalized interest cannot earn interest on itself that day.
Post one credit per account for a positive total with value date 6. A zero total
needs no financial entry. Repeated finalization must not post twice. Reject new
events after finalization; reopening a capitalized window is outside this design.

DailyCloseService.daily_accruals returns a six-day projection at the requested
recording cutoff, even before all days close; only finalization makes it final.
INTEREST postings are excluded from the basis, keeping repeated queries consistent
with the capitalization total. Finalization state is an append-only control marker,
not a boolean that disappears when a service instance is reconstructed. Late input
attempts after that marker remain audited with REJECTED decisions and no postings.

## 11. Rounding and excess input precision

Use Decimal from text, never binary floating point. Use ROUND_HALF_UP at the
currency's scale. Reject transaction inputs with nonzero sub-minor-unit digits
rather than silently changing the requested amount; trailing zeroes are harmless.
Derived interest is rounded explicitly. Reject non-finite amounts and nonpositive
transaction amounts; openings and balances may be zero, and postings may be signed.

## 12. Equal instalments at finite precision

Exact equality is impossible for 10.000 divided by three at BHD precision.
Divide integer minor units and distribute remaining units in instalment order.
The first instalment gets 3.334, then 3.333 and 3.333. Validate all postings before
appending any. Preserve the parent input event and each child posting.

Step 3 detail: every instalment must be positive, so reject counts exceeding the
number of minor units rather than creating zero-value postings. Only CREDIT
supports multiple instalments. This is a chosen bounded API contract; the supplied
E10 satisfies it. Full reversal of an instalment credit creates one compensating
posting for its complete total, linked to the parent event.

## 13. BHD overdraft pricing

Only an AED fee is supplied. Do not apply AED 25 as BHD 25 or invent conversion.
If a BHD negative close is encountered, report an unsupported-fee-policy error
and do not silently claim a completed fee assessment. The supplied BHD stream
never goes negative. General multi-currency overdraft pricing is unsupported.

Step 5 implementation: an unsupported negative close appends a FEE_ERROR identifying
account and assessment day, once for that account/day. It returns an incomplete
close/finalization result, with no FINALIZED marker or interest capitalization.
Input processing continues to permit a correcting reversal. Earlier fee-error
records remain even if a correction resolves the condition; finalization's result
reports whether the current condition is resolved. No cross-account transaction
rollback is promised for closing: supported AED fees may already have been booked
while another account's pricing remains unresolved.

## 14. Duplicates, identity, and invalid events

Event IDs are unique across the stream; authorization IDs are scoped by account.
Keep duplicate attempts in the input audit but reject repeated financial effects.
Reserve an event ID on its first attempt, including a rejected attempt. Record
unknown accounts, currency mismatches, bad references, and invalid dates as errors.
Validate references against the original account and operation. Reject a second
settlement or second reversal. Supported reversals initially target ordinary
credit/debit postings; reversal of settlement lifecycles or fee entries is not
implicitly supported. E7 is a supported ordinary debit.

Step 3 detail: a full reversal must match the original value date and must not
supply an amount; derive that amount from the original financial postings.
References to rejected events have no postings to reverse. References across
accounts, to reversals, or to already-reversed events are rejected. Unrelated
authorization/reference fields on ordinary postings are rejected rather than
silently ignored. Ordinary debits may overdraw; the nonnegative-availability
rule is for authorization requests, not a blanket debit restriction.

## 15. Dates outside the window

Use integer day numbers 1 through 6 for this exercise. Reject out-of-window and
future-value input dates (value day later than booked day); those operations
would require an explicit scheduling policy. No real calendar, timezone, or
bank-holiday rules are inferred. Worklog timestamps use real UTC separately.

## 16. Append-only and atomicity boundary

Frozen records and tuple snapshots protect the public interface; internal
collections are private. Validate an entire operation before its financial
postings are appended. Invalid operations append errors without partial money
movement. This is single-threaded in-memory business atomicity, not durability,
crash recovery, tamper-proof storage, or concurrent writer support.

Step 2 detail: AccountModel, EventModel, EntryModel, DecisionModel, and the journal
envelope are frozen dataclasses with scalar fields. Validated money is normalized
only during record construction, never after appending. Input records preserve
invalid business values (such as an unknown currency or out-of-window integer
day) for later service rejection. Invalid field types or mutable payloads fail
record construction; this typed core does not promise to ingest arbitrary objects.
The service will distinguish valid record construction from business acceptance.

Every appended record receives a journal sequence, including input attempts and
decisions. A historical cutoff is inclusive and must refer to an existing sequence
or zero. A future cutoff is rejected to avoid accidentally claiming future knowledge.
The data client permits repeated input IDs for audit; financial duplicate handling
belongs to the service, not an implicit storage deduplication rule.

## 17. Reporting historical versus final information

Print original daily snapshots and explicit correction checkpoints, then final
restated daily results. Label day, account, and recording cutoff. A Day 2 fee can
coexist with a now-positive restated Day 2 balance after E9 because fees were
retained. Do not present an error's booked date as its arrival position.

## 18. Test suite and intentional failure

Keep passing behavioral tests separate from one visible, deliberately failing
partial-settlement test. Do not mark it xfail, skip it secretly, or disguise an
import error as the required failure. Default full discovery includes it. The
README will give both passing-suite and deliberate-failure commands.

## 19. Repository history and genuine worklog

The author will create and commit the repository after reviewing each stage.
AI will not commit, squash, backdate, or fabricate time spent. Document real
implementation timestamps and distinguish design alternatives from approaches
actually abandoned during implementation.
