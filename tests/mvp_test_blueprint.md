# MVP Test Blueprint

This document converts the MVP requirements into a concrete test file layout, fixtures plan, and assertion checklist.

## Test Directory Layout

```text
tests/
  conftest.py
  fixtures/
    sources.yaml
    buckets.yaml
    bookmarks_chrome.html
    bookmarks_firefox.html
    media/
      audio_tagged.mp3
      audio_untagged.wav
      video_captioned.mp4
      video_nocaption.mp4
      doc_notes.txt
      hidden/.DS_Store
      nested/project/readme.md
  unit/
    test_config_sources.py
    test_config_buckets.py
    test_bookmark_parser.py
    test_file_classifier.py
    test_audio_metadata_chunk.py
    test_video_metadata_chunk.py
    test_ocr_scheduler.py
    test_ocr_filtering.py
    test_bucket_rule_matchers.py
    test_bucket_scoring.py
    test_embedding_dedup.py
  integration/
    test_init_db_schema.py
    test_ingest_folders.py
    test_ingest_bookmarks.py
    test_chunk_fts_sync.py
    test_assign_buckets.py
    test_embed_pipeline.py
    test_ocr_pipeline.py
  e2e/
    test_cli_happy_path.py
    test_cli_search_modes.py
    test_cli_debug_commands.py
```

## Shared Fixtures (`tests/conftest.py`)

- `tmp_workspace`:
  - creates isolated temp directory with:
    - `config/`
    - `data/`
    - `archive/`
- `seed_media_archive`:
  - copies fixture files into nested archive paths.
- `seed_sources_yaml`:
  - writes `config/sources.yaml` with folder + bookmark sources.
- `seed_buckets_yaml`:
  - writes `config/buckets.yaml` with source/topic/status buckets including `review_later` fallback.
- `db_path`:
  - points to `data/archive_index.kuzu`.
- `run_cli` helper:
  - executes `python -m archive_indexer ...` in temp workspace and captures stdout/stderr/exit code.
- `mock_ollama_embed`:
  - deterministic fake embed API response (stable vector length and values).
- `mock_ocr_engine`:
  - deterministic OCR output keyed by video + timestamp.

## Unit Test Blueprint

## `unit/test_config_sources.py`

- `test_load_multiple_sources_from_yaml`
- `test_reject_source_missing_required_field`
- `test_reject_unknown_source_type`
- `test_normalize_source_paths`

Assertions:
- parsed source count matches YAML
- schema errors include field names

## `unit/test_config_buckets.py`

- `test_load_bucket_definitions_and_rules`
- `test_reject_duplicate_bucket_names`
- `test_validate_supported_rule_types_only`
- `test_require_single_fallback_bucket_or_none`

Assertions:
- all rules have type/pattern/weight defaults
- unsupported rules fail fast

## `unit/test_bookmark_parser.py`

- `test_parse_chrome_bookmark_html`
- `test_parse_firefox_bookmark_html`
- `test_extract_domain_and_folder_path`
- `test_handles_missing_add_date`
- `test_skips_invalid_url_rows`

Assertions:
- title/url/domain/folder path extracted as expected

## `unit/test_file_classifier.py`

- `test_audio_extension_detection`
- `test_video_extension_detection`
- `test_unknown_extension_falls_back_generic`
- `test_hidden_file_detection`

Assertions:
- extensions map to expected item types

## `unit/test_audio_metadata_chunk.py`

- `test_build_audio_metadata_chunk_with_tags`
- `test_build_audio_metadata_chunk_without_tags`
- `test_does_not_invoke_transcription_path`

Assertions:
- chunk contains path/filename/folders/duration
- no transcription fields or calls are made

## `unit/test_video_metadata_chunk.py`

- `test_build_video_metadata_chunk`
- `test_handles_missing_codec_gracefully`

Assertions:
- duration/resolution/extension present in chunk text

## `unit/test_ocr_scheduler.py`

- `test_frame_schedule_every_n_seconds`
- `test_respects_max_frames_per_video`
- `test_handles_short_videos`

Assertions:
- generated timestamps are bounded and monotonic

## `unit/test_ocr_filtering.py`

- `test_skip_empty_ocr_text`
- `test_skip_below_min_char_threshold`
- `test_accept_text_above_threshold`

Assertions:
- only valid OCR chunks pass filtering

## `unit/test_bucket_rule_matchers.py`

One test per rule type:
- `path_regex`
- `filename_regex`
- `folder_regex`
- `extension`
- `mime_type`
- `domain_regex`
- `bookmark_folder_regex`
- `text_regex`

Assertions:
- positive and negative cases for each matcher

## `unit/test_bucket_scoring.py`

- `test_score_sums_weights`
- `test_confidence_clamped_to_one`
- `test_confidence_uses_threshold`
- `test_no_match_returns_zero_confidence`

Assertions:
- confidence math exactly matches `min(score/threshold, 1.0)`

## `unit/test_embedding_dedup.py`

- `test_skip_existing_embedding_same_model`
- `test_regenerate_when_model_changes`
- `test_one_embedding_per_chunk_per_model`

Assertions:
- dedup key is `(chunk_id, model)`

## Integration Test Blueprint

## `integration/test_init_db_schema.py`

- run `init-db`
- assert required tables exist:
  - `sources`, `items`, `chunks`, `bucket_definitions`, `bucket_rules`, `item_buckets`, `embeddings`, `chunk_fts`

Assertions:
- key columns exist for each table
- FTS5 virtual table is queryable

## `integration/test_ingest_folders.py`

- run `init-db`, then `ingest`
- assert recursive files ingested
- assert hidden/system files ignored by default
- re-run ingest unchanged and assert no duplicate item rows
- touch one file and re-run ingest to verify selective update

Assertions:
- `items.path_or_url` unique
- row deltas match change set

## `integration/test_ingest_bookmarks.py`

- run `ingest-bookmarks` against both fixture HTML formats
- assert one item + one bookmark chunk per bookmark

Assertions:
- chunk text includes title/url/domain/folder

## `integration/test_chunk_fts_sync.py`

- after ingest/chunking, query FTS table directly
- verify every created chunk has corresponding FTS row

Assertions:
- `chunks.id` and `chunk_fts.chunk_id` parity

## `integration/test_assign_buckets.py`

- load fixtures buckets config
- run `assign-buckets`
- verify:
  - multi-bucket assignment works
  - confidence stored
  - evidence JSON stored and non-empty for matches
  - fallback `review_later` assigned for low-signal item
- modify buckets config and re-run assignment

Assertions:
- updated rules change `item_buckets` outcomes without re-ingest

## `integration/test_embed_pipeline.py`

- mock Ollama endpoint
- run embed once, assert embedding rows inserted
- run embed again with same model, assert no duplicate inserts
- switch model in settings, run embed, assert additional rows for new model

Assertions:
- dimensions + model persisted as expected

## `integration/test_ocr_pipeline.py`

- mock OCR engine and frame extraction
- run `ocr-videos`
- assert:
  - frame cache files created when enabled
  - `frame_ocr` chunks inserted with timestamps
  - low-quality/empty OCR omitted
  - OCR chunks visible in FTS

Assertions:
- chunk timestamp fields are non-null for OCR chunks

## E2E CLI Blueprint

## `e2e/test_cli_happy_path.py`

Flow:
1. `init-db`
2. `ingest`
3. `assign-buckets`
4. `search "ollama embeddings"`

Assertions:
- all commands return success exit code
- search returns at least one relevant seeded item

## `e2e/test_cli_search_modes.py`

- keyword search baseline
- `--bucket` filter search
- `embed` + `search --semantic`
- verify OCR timestamp is shown when OCR chunk matched

Assertions:
- output includes path/url, buckets, matched chunk text

## `e2e/test_cli_debug_commands.py`

- `show-item PATH_OR_URL`
- `explain-buckets PATH_OR_URL`
- `list-bucket review_later`
- `bucket-stats`

Assertions:
- outputs are parseable and include expected key fields

## Per-Feature Coverage Map

- Source configuration: `unit/test_config_sources.py`, `integration/test_ingest_folders.py`
- Folder crawler: `unit/test_file_classifier.py`, `integration/test_ingest_folders.py`
- Bookmark parser: `unit/test_bookmark_parser.py`, `integration/test_ingest_bookmarks.py`
- Audio metadata indexing: `unit/test_audio_metadata_chunk.py`, `integration/test_chunk_fts_sync.py`
- Video metadata indexing: `unit/test_video_metadata_chunk.py`, `integration/test_chunk_fts_sync.py`
- Video frame OCR: `unit/test_ocr_scheduler.py`, `unit/test_ocr_filtering.py`, `integration/test_ocr_pipeline.py`
- Bucket configuration: `unit/test_config_buckets.py`, `integration/test_assign_buckets.py`
- Rule-based assignment: `unit/test_bucket_rule_matchers.py`, `unit/test_bucket_scoring.py`, `integration/test_assign_buckets.py`
- Kuzu storage: `integration/test_init_db_schema.py`, `integration/test_chunk_fts_sync.py`
- Ollama embeddings: `unit/test_embedding_dedup.py`, `integration/test_embed_pipeline.py`
- Search CLI: `e2e/test_cli_happy_path.py`, `e2e/test_cli_search_modes.py`

## Minimum CI Stages

1. **fast-unit**: `pytest tests/unit -q`
2. **integration**: `pytest tests/integration -q`
3. **e2e**: `pytest tests/e2e -q`

Suggested temporary markers:
- `@pytest.mark.unit`
- `@pytest.mark.integration`
- `@pytest.mark.e2e`
- `@pytest.mark.requires_ollama` (should be mocked in CI for MVP)
- `@pytest.mark.requires_ffmpeg` (if real frame extraction is used)

## Definition of Complete Test Planning

Planning is complete when:
- every MVP feature has at least one unit/integration/e2e target test
- each CLI command in MVP command list is covered by at least one integration or e2e test
- all non-goals are guarded by tests (e.g., no Whisper invocation)
- idempotency is verified for ingest/embed/assign where applicable
