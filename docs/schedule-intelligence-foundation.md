# Schedule Intelligence Foundation

Brunel preserves structured schedules as immutable, project-scoped revisions. CSV is the deterministic baseline; constrained synthetic Primavera/Microsoft-style XML and core `%T`/`%F`/`%R` XER tables are adapter foundations. Original fields, row/table identity, parser version, content hashes, and normalized values remain traceable.

Activities, milestones, relationships, lags, constraints, codes, source float, and source dates remain distinct from Brunel calculations. Quality assessment flags incomplete logic, calendars, dates, progress, constraints, duration, identity, and float without certifying the schedule. CPM runs only with interpretable durations, valid acyclic logic, and imported calendars or an explicit approximate calendar-day fallback. Brunel never claims P6 or Microsoft Project parity.

Stable lineage uses source IDs plus conservative name/WBS similarity and preserves ambiguity for review. Comparisons report additions, removals, date movement, duration, float, constraint, WBS, name, and progress changes with old/new citations. These findings are not forensic analysis and do not establish delay, cause, responsibility, concurrency, excusability, compensability, critical path, or entitlement.

Canonical links connect activities to procurement, submittals, RFIs, changes, drawings, meetings, decisions, and commissioning references. Synchronization records are proposals only: acceptance records the human decision but does not silently alter downstream dates. There is no schedule write-back endpoint.

The development API and `schedule-*` CLI expose import, schedules/revisions, quality, activities, relationships, milestones, criticality views, lineage review, comparisons, look-ahead, links, proposals, dashboard, register, and search. Audit and notifications remain local. External models, notification delivery, platform integrations, resource/cost loading, recovery planning, claims analysis, and a frontend are not included.
