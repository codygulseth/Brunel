# Risk & Commitment Intelligence

Risk & Commitment Intelligence is Brunel's deterministic, project-scoped cross-system review layer. It stores risk candidates, normalized commitment views, mitigation proposals, dependency edges, audit events, and local-only notification requests. It references canonical source records by stable ID and citation; it does not duplicate or mutate documents, schedules, procurement, submittal, RFI, meeting, change, or daily-report records.

Candidates begin as `proposed`. Deterministic correlation distinguishes strong identifier/location/system signals from weak candidate links, which always require review. Severity and likelihood are transparent proposals with factors, confidence, and uncertainty. Humans can confirm for monitoring, reject, mitigate, close, or reopen a candidate. Completion of a normalized commitment requires reviewable evidence.

The dependency view exposes upstream blockers and downstream exposure using cited edges. Dashboard and Q&A responses remain project-scoped and distinguish candidates from human-confirmed records. Notifications are persisted only to Brunel's local outbox.

## Limits

Brunel does not determine delay, responsibility, fault, entitlement, cost liability, critical-path impact, engineering/code/safety compliance, product approval, corrective action, or schedule changes. It does not send external communications or update downstream workflows. These outputs are evidence-backed proposals for human review.
