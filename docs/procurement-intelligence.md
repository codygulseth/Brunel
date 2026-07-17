# Procurement Intelligence

Brunel's canonical `procurement` domain provides evidence-backed candidate review, a project procurement register, lead-time history, transparent date planning, dependencies, milestones, release readiness, versioned forecasts, explainable exposure, delivery visibility, staleness, snapshots, and comparisons.

Candidates are deterministic proposals extracted from cited project statements and remain non-authoritative until reviewed. Stable project-scoped `PROC-###` numbers are assigned only when a human admits or manually creates an item. Existing submittal product/package records, RFIs, revisions, drawings, meeting actions, project changes, and schedule activities are linked by stable IDs; they are not copied into a second architecture.

## Planning and evidence

Lead-time evidence preserves definition, duration, basis, source, effective dates, confidence, confirmation, and supersession. Unlike definitions are never silently combined. Required-on-site records preserve whether a date is a schedule relationship, meeting commitment, user target, or planning assumption.

Calendar-day planning derives ship, ready-to-ship, fabrication-start, release, approval, and submit dates only when required inputs are present. The formulas subtract receiving/buffer, shipping, fabrication, procurement processing, correction, design review, resubmittal, and internal review allowances in that order. Every calculation stores its inputs, missing inputs, warnings, timestamp, calendar mode, and policy version. Derived dates are planning calculations, not contractual schedule dates.

## Human authority and lifecycle

Release readiness is a Brunel assessment. Release authorization is a separate human record. `ready_for_release` never means authorized to buy, an approved submittal does not equal authorization, and `released` cannot be recorded without explicit human authorization. Delivery and acceptance are distinct, as are storage, installation readiness, installation, and closure.

Exposure is deterministic and explainable. It may report potential exposure, insufficient information, negative float, open dependencies, stale evidence, or forecast variance; it never asserts a confirmed project delay without an explicit human record. Forecasts, lead times, date plans, deliveries, audit events, and plan snapshots preserve history.

## Interfaces and limitations

The development API exposes candidate extraction/review; item creation, filtering, transition, lead times, dependencies, milestones, forecasts, date plans, readiness, authorization, delivery, staleness and audit; plus register, dashboard, exposure, snapshot and comparison routes. Matching `procurement-*` CLI commands cover the primary operator workflow. Persistence uses the existing atomic local JSON pattern and notification requests remain in a local outbox.

Brunel does not place purchase orders, approve suppliers or products, commit funds, confirm pricing, release procurement automatically, modify schedules, determine contractual entitlement, or treat estimates as guarantees. Commercial values are human-entered. External model calls, notification delivery, ERP/email/platform integrations, supplier scoring, CPM parsing, and a frontend are not included.
