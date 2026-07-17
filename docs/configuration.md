# Configuration

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

