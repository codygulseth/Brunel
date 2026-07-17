# Configuration

Meeting extraction is deterministic by default. No external model provider is selected, and notification requests remain in the local outbox. Meeting storage uses the configured Brunel data directory; generated minutes exports belong under ignored report directories.

Drawing artifacts use the configured Brunel data directory. OCR remains disabled unless a composition root explicitly injects a provider. External OCR/model processing is never selected implicitly. Title-block templates are versioned and may be explicitly selected during ingestion.

Brunel reads immutable settings from `BRUNEL_*` environment variables. Defaults run entirely locally and require no secrets. See `config/example.env` for a copyable reference.

## Retrieval

| Variable | Default | Purpose |
| --- | ---: | --- |
| `BRUNEL_RETRIEVAL_TOP_K` | `5` | Default maximum ranked chunks |
| `BRUNEL_MINIMUM_RELEVANCE` | `0.08` | Minimum normalized local score |
| `BRUNEL_CITATION_EXCERPT_LENGTH` | `320` | Maximum exact citation excerpt characters |
| `BRUNEL_MAXIMUM_EVIDENCE_CHUNKS` | `8` | Evidence cap passed to answering |

## Answer providers

`BRUNEL_ANSWER_PROVIDER=extractive` is the safe default. It uses no model or network and quotes the highest-ranked supplied evidence.

To use an explicitly configured OpenAI-compatible endpoint:

```text
BRUNEL_ANSWER_PROVIDER=openai_compatible
BRUNEL_MODEL_BASE_URL=https://provider.example/v1
BRUNEL_MODEL_NAME=configured-model-name
BRUNEL_MODEL_API_KEY=<set outside Git>
BRUNEL_MODEL_TEMPERATURE=0.1
BRUNEL_STRUCTURED_OUTPUT_RETRY_LIMIT=1
```

The API key must be supplied through the runtime environment or secret manager and must never be committed. Structured output is validated with Pydantic. Invalid output is retried only up to the configured limit, then the answering service returns a safe `failed` response rather than unvalidated text.

## Storage and logging

- `BRUNEL_DATA_DIRECTORY` selects the local data root; ingestion records default to `data/ingested`.
- `BRUNEL_LOG_LEVEL` controls verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`.
- `BRUNEL_LOG_JSON=true` enables structured JSON logs with project and retrieval context.

## Revision Intelligence

| Variable | Default | Purpose |
| --- | ---: | --- |
| `BRUNEL_REVISION_ALIGNMENT_THRESHOLD` | `0.55` | Minimum block-match score |
| `BRUNEL_REVISION_AMBIGUOUS_THRESHOLD` | `0.08` | Near-tie ambiguity margin |
| `BRUNEL_REVISION_MINIMUM_SIMILARITY` | `0.35` | Comparability baseline |
| `BRUNEL_REVISION_MAXIMUM_BLOCK_SIZE` | `2000` | Normalization block cap |
| `BRUNEL_REVISION_INCLUDE_FORMATTING` | `false` | Include formatting-only findings |
| `BRUNEL_REVISION_MAXIMUM_EXCERPT_LENGTH` | `500` | Report excerpt limit |
| `BRUNEL_REVISION_MINIMUM_SEVERITY` | `low` | Default report policy |
| `BRUNEL_REPORT_OUTPUT_DIRECTORY` | `reports` | Generated report root |
| `BRUNEL_REVISION_RULES_VERSION` | `construction-rules-v1` | Explainable ruleset |

Comparison is local by default. `--use-model` sends no content in this version; it warns and falls back deterministically.

## Revision review workflow

| Variable | Default | Purpose |
| --- | ---: | --- |
| `BRUNEL_AUTO_REGISTER_GENERATION` | `false` | Explicitly enable post-comparison admission orchestration |
| `BRUNEL_ADMISSION_POLICY_VERSION` | `change-admission-v1` | Versioned deterministic materiality rules |
| `BRUNEL_DEFAULT_REVIEW_PRIORITY` | `medium` | Manual-record default policy |
| `BRUNEL_DUE_SOON_DAYS` | `7` | Dashboard due-soon boundary |
| `BRUNEL_AUTO_REGENERATION` | `false` | Explicitly enable synchronous regeneration |
| `BRUNEL_NOTIFICATION_OUTBOX` | `true` | Queue local notification requests only |
| `BRUNEL_API_HOST` | `127.0.0.1` | Development API bind host |
| `BRUNEL_API_PORT` | `8001` | Development API port |
| `BRUNEL_API_PAGE_LIMIT` | `50` | Default bounded list size |
| `BRUNEL_LEGACY_COMPATIBILITY` | `true` | Retain deprecated prototype compatibility |

## RFI automation

| Variable | Default | Purpose |
| --- | ---: | --- |
| `BRUNEL_RFI_NUMBER_PREFIX` | `RFI` | Project RFI numbering prefix |
| `BRUNEL_RFI_NUMBER_DIGITS` | `3` | Zero-padded sequence width |
| `BRUNEL_RFI_NUMBER_AT_CREATION` | `true` | Reserve numbers when drafts are created |
| `BRUNEL_RFI_MODEL_ASSISTANCE` | `false` | Allow an explicitly injected optional draft provider |
| `BRUNEL_RFI_DUPLICATE_THRESHOLD` | `0.72` | Similar-question review indicator threshold |
| `BRUNEL_RFI_DEFAULT_REQUIRED_DAYS` | `10` | Delivery-adapter default response interval |
| `BRUNEL_RFI_EXPORT_DIRECTORY` | `reports/rfis` | Ignored generated export root |

The current local service always works deterministically. Enabling the model flag alone does not configure or call a provider; a provider must be explicitly injected at composition time. Notifications remain local outbox records even when `BRUNEL_NOTIFICATION_OUTBOX=true`.

## Submittal automation

| Variable | Default | Purpose |
| --- | ---: | --- |
| `BRUNEL_SUBMITTAL_NUMBER_PREFIX` | `SUB` | Project register numbering prefix |
| `BRUNEL_SUBMITTAL_NUMBER_DIGITS` | `3` | Zero-padded sequence width |
| `BRUNEL_SUBMITTAL_NUMBER_MODE` | `sequential` | `sequential` or specification-section prefix mode |
| `BRUNEL_SUBMITTAL_MODEL_ASSISTANCE` | `false` | Permit explicitly injected optional extraction assistance |
| `BRUNEL_SUBMITTAL_REAPPROVAL_AFTER_CHANGE` | `true` | Document the current mandatory package-reapproval policy |
| `BRUNEL_SUBMITTAL_DUE_SOON_DAYS` | `7` | Local deadline-notification horizon |
| `BRUNEL_SUBMITTAL_CALENDAR_MODE` | `calendar_days` | Deterministic date-calculation basis |
| `BRUNEL_SUBMITTAL_EXPORT_DIRECTORY` | `reports/submittals` | Ignored generated export root |
| `BRUNEL_SUBMITTAL_ATTACHMENT_DIRECTORY` | `attachment-files` | Immutable local binary root below the data directory |
| `BRUNEL_SUBMITTAL_ATTACHMENT_MAX_BYTES` | `52428800` | Maximum accepted attachment size |
| `BRUNEL_SUBMITTAL_ATTACHMENT_EXTRACTOR_VERSION` | `attachment-extractor-v1` | Recorded extraction policy identity |
| `BRUNEL_SUBMITTAL_ATTACHMENT_MAPPING_POLICY` | `deterministic-cited-mapping-v1` | Recorded mapping policy identity |

Submittal extraction and completeness run deterministically without a model. Setting the assistance flag alone cannot call an external provider; composition must also inject one. Notifications are local outbox records, and procurement release always requires a human service action.

