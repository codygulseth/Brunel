# Meeting Minutes and Action Tracking

Brunel stores meeting notes, agendas, transcripts, and minutes through canonical immutable `SourceDocument` revisions. A meeting-specific analysis attaches cited agenda items and item proposals; it does not replace or rewrite the source.

Deterministic parsers identify explicit actions, decisions, questions, risks, blockers, commitments, dependencies, workflow identifiers, owners, and due-date text. Each result is a proposal with exact page/chunk evidence and requires human review. Unknown owners and dates remain unknown. Potential cost or schedule language is not promoted to a confirmed impact.

Confirmed actions enter a project-scoped action register with explicit assignment and transition rules. Omission from a later meeting never marks an action complete. Confirmed decisions remain separate from proposals; possible conflicts preserve both sources and Brunel does not decide contractual precedence. Workflow links are explicit and do not create or issue RFIs, submittals, procurement actions, schedule changes, or project changes.

Minutes drafting uses confirmed items by default. Draft, review, approval, and internal issue are explicit human actions. Issued content retains its hash and corrections require another revision. No email or external distribution occurs.

The development API and CLI expose meeting creation, immutable record ingestion, analysis, proposal review, action assignment/transitions, decision confirmation, minutes workflows, comparisons, dashboards, and search. Audio/video transcription, calendar/conferencing integrations, external models, and a frontend are out of scope.

Meeting records may conflict with RFIs or contract documents. Brunel labels evidence authority and does not determine which record governs. External model calls and external notification delivery are disabled by default.
