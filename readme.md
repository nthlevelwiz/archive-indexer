# Archive Indexer

A local-first indexing system for old saved TikToks, videos, audio files, documents, downloads, and browser bookmarks.

The goal is to turn messy folders and bookmark exports into a searchable local archive using deterministic metadata extraction, configurable buckets, OCR from video frames, SQLite, and Ollama embeddings.

This project does **not** try to fully understand every file. It creates useful searchable “index cards” from filenames, folder paths, metadata, bookmark titles, URLs, and video frame text.


---

## Getting Started

1. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   ```

2. **Initialize the database**

   ```bash
   python -m archive_indexer init-db
   ```

3. **Create or update source config** in `config/sources.yaml` with your folder paths and bookmark export files.

4. **Ingest content**

   ```bash
   python -m archive_indexer ingest
   ```

5. **Assign buckets**

   ```bash
   python -m archive_indexer assign-buckets
   ```

6. **Run a keyword search**

   ```bash
   python -m archive_indexer search "ollama embeddings"
   ```

7. **(Optional) Generate embeddings for semantic search**

   ```bash
   python -m archive_indexer embed
   python -m archive_indexer search "local ai vector search" --semantic
   ```

---

## Goals

* Index old folders, saved videos, TikToks, audio files, documents, and bookmark exports.
* Use local tooling where possible.
* Use Ollama for embeddings and optional semantic search.
* Keep bucket assignment transparent and debuggable.
* Avoid Whisper or audio transcription for the MVP.
* Extract video text by periodically sampling frames and running OCR.
* Store everything in a local SQLite database.
* Make it easy to add, remove, or revise buckets over time.

---

## Non-Goals for MVP

The MVP should **not** attempt to do everything.

Out of scope for the first version:

* Audio transcription with Whisper.
* Full webpage crawling for every bookmark.
* Automatic duplicate cleanup or deletion.
* Fancy web UI.
* Cloud sync.
* Face recognition.
* Object detection in video frames.
* Automatic file moving or reorganization.
* Complex machine-learning classification beyond simple rule-based buckets and embeddings.

---

## Core Concept

Each source produces items. Each item produces searchable chunks. Chunks can be embedded with Ollama. Items are assigned to buckets using configurable rules.

```text
source folder / bookmark export
        ↓
item: one file, video, audio file, image, document, or bookmark
        ↓
chunks: searchable text extracted from that item
        ↓
bucket assignment: rule-based labels with evidence
        ↓
embeddings: Ollama vector representation of each chunk
        ↓
search: keyword search + semantic search + bucket filtering
```

---

## Example

A saved TikTok video:

```text
/archive/old_tiktoks/saved/video_8392.mp4
```

Might become:

```text
Item:
  type: video
  path: /archive/old_tiktoks/saved/video_8392.mp4

Chunks:
  - path_metadata
  - video_metadata
  - frame_ocr at 00:00:05
  - frame_ocr at 00:00:10
  - frame_ocr at 00:00:15

Buckets:
  - tiktok_saved
  - electrical
  - career

Embeddings:
  - one embedding per searchable chunk
```

Then a query like:

```text
electrical apprenticeship advice video
```

Could return:

```text
/archive/old_tiktoks/saved/video_8392.mp4
Matched frame OCR at 00:00:10:
"how I got into the electrical trade without experience"
Buckets: tiktok_saved, electrical, career
```

---

## MVP Features

### 1. Source Configuration

Define sources in a config file.

Example `config/sources.yaml`:

```yaml
sources:
  - label: Old TikToks
    type: folder
    path: /archive/old_tiktoks

  - label: Audio Projects
    type: folder
    path: /archive/audio_projects

  - label: Chrome Bookmarks
    type: bookmark_html
    path: /archive/bookmarks/chrome_bookmarks.html
```

MVP requirement:

* Read one or more folder paths.
* Read one or more bookmark HTML exports.
* Store each configured source in the database.

---

### 2. Folder Crawler

The folder crawler should walk configured directories and create one `items` row per file.

For each file, collect:

* Absolute path.
* Filename.
* Extension.
* File size.
* Modified time.
* Basic MIME type if available.
* Optional content hash.

MVP requirement:

* Recursively scan folders.
* Ignore hidden/system files by default.
* Avoid re-indexing unchanged files.
* Record files in SQLite.

---

### 3. Bookmark Parser

The bookmark parser should read browser bookmark HTML exports.

For each bookmark, collect:

* Title.
* URL.
* Domain.
* Bookmark folder path.
* Add date if available.

MVP requirement:

* Parse Chrome/Firefox-style bookmark HTML.
* Create one `items` row per bookmark.
* Create a searchable chunk from title, URL, domain, and bookmark folder path.

---

### 4. Audio Metadata Indexing

Audio files should **not** be transcribed in the MVP.

For audio, create searchable text from:

* File path.
* Filename.
* Parent folders.
* Extension.
* Duration.
* Artist/title/album/date metadata if available.
* Sample rate, bitrate, or codec if available.

Example audio chunk:

```text
TYPE: audio_metadata
PATH: /archive/music/sketches/140bpm garage wobble.wav
FILENAME: 140bpm garage wobble.wav
FOLDERS: archive, music, sketches
EXTENSION: wav
DURATION: 00:02:31
TAGS: 140bpm, garage, wobble
```

MVP requirement:

* Identify common audio extensions.
* Extract metadata where available.
* Create one searchable `audio_metadata` chunk per audio file.
* Do not run Whisper.

Common audio extensions:

```text
.mp3, .wav, .flac, .aiff, .ogg, .m4a, .aac, .mid, .midi
```

---

### 5. Video Metadata Indexing

For videos, create a metadata chunk from:

* Path.
* Filename.
* Parent folders.
* Extension.
* Duration.
* Width and height.
* Codec/container if available.

Example video metadata chunk:

```text
TYPE: video_metadata
PATH: /archive/old_tiktoks/saved/video_8392.mp4
FILENAME: video_8392.mp4
FOLDERS: archive, old_tiktoks, saved
DURATION: 38 seconds
RESOLUTION: 1080x1920
EXTENSION: mp4
```

MVP requirement:

* Identify common video extensions.
* Extract basic video metadata.
* Create one searchable `video_metadata` chunk per video.

Common video extensions:

```text
.mp4, .mov, .mkv, .webm, .avi, .m4v
```

---

### 6. Video Frame OCR

For videos, periodically sample frames and run OCR on those frames.

Default MVP behavior:

```text
sample one frame every 5 seconds
```

For each OCR result, create a chunk:

```text
TYPE: frame_ocr
VIDEO: /archive/old_tiktoks/saved/video_8392.mp4
TIMESTAMP: 00:00:10
OCR TEXT: how I got into the electrical trade without experience
```

MVP requirement:

* Use a configurable frame interval.
* Cache extracted frames.
* Run OCR on sampled frames.
* Store OCR text as `frame_ocr` chunks.
* Store approximate timestamp for each OCR chunk.
* Skip frames where OCR text is empty or too low quality.

Recommended config:

```yaml
video:
  frame_interval_seconds: 5
  max_frames_per_video: 120
  ocr_min_chars: 5
  cache_frames: true
```

---

### 7. Bucket Configuration

Buckets should be hardcoded enough to be useful but flexible enough to revise.

Buckets live in `config/buckets.yaml`.

Example:

```yaml
buckets:
  - name: tiktok_saved
    bucket_type: source
    description: Saved TikToks and downloaded vertical videos
    rules:
      - type: path_regex
        pattern: "(?i)tiktok|saved videos|douyin"
        weight: 2.0
      - type: extension
        pattern: ".mp4"
        weight: 0.2
      - type: extension
        pattern: ".mov"
        weight: 0.2

  - name: music_production
    bucket_type: topic
    description: DAW projects, samples, stems, loops, and music sketches
    rules:
      - type: path_regex
        pattern: "(?i)reaper|ableton|samples|stems|loops|garage|dubstep"
        weight: 2.0
      - type: filename_regex
        pattern: "(?i)bpm|stem|loop|bass|drum|kick|snare|midi"
        weight: 1.0
      - type: extension
        pattern: ".wav"
        weight: 0.5
      - type: extension
        pattern: ".mid"
        weight: 0.5

  - name: electrical
    bucket_type: topic
    description: Electrical work, NEC, trade school, wiring, and panels
    rules:
      - type: path_regex
        pattern: "(?i)electrical|nec|wiring|commercial"
        weight: 2.0
      - type: text_regex
        pattern: "(?i)nec|conduit|breaker|panel|service|feeder|branch circuit|electrician"
        weight: 1.5

  - name: local_ai
    bucket_type: topic
    description: Ollama, local LLMs, embeddings, vector search, and RAG
    rules:
      - type: text_regex
        pattern: "(?i)ollama|embedding|vector|rag|chroma|llm|open webui|openwebui"
        weight: 1.5
      - type: path_regex
        pattern: "(?i)ollama|local.?ai|llm|openwebui"
        weight: 2.0

  - name: review_later
    bucket_type: status
    description: Items that did not confidently match anything
    fallback: true
```

MVP requirement:

* Load bucket definitions from YAML.
* Support multiple buckets per item.
* Store confidence scores.
* Store evidence explaining why each bucket was assigned.
* Assign `review_later` when no bucket confidently matches.

---

### 8. Rule-Based Bucket Assignment

Supported MVP rule types:

```text
path_regex
filename_regex
folder_regex
extension
mime_type
domain_regex
bookmark_folder_regex
text_regex
```

Scoring model:

```text
bucket score = sum of matching rule weights
confidence = min(score / threshold, 1.0)
```

Suggested default threshold:

```text
3.0
```

Example:

```text
path matched tiktok_saved: +2.0
extension .mp4: +0.2
score = 2.2
confidence = 0.73
```

MVP requirement:

* Evaluate item-level rules against path, filename, folders, extension, MIME type, and bookmark domain.
* Evaluate text rules against chunks.
* Save all matched rules as evidence.
* Allow rules to be changed and bucket assignment rerun without re-extracting all files.

---

### 9. SQLite Storage

The MVP uses SQLite as the main database.

Minimal schema:

```sql
CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  root_path_or_file TEXT NOT NULL,
  label TEXT,
  config_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE items (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  item_type TEXT NOT NULL,
  path_or_url TEXT NOT NULL UNIQUE,
  filename TEXT,
  extension TEXT,
  mime_type TEXT,
  size_bytes INTEGER,
  modified_time TEXT,
  content_hash TEXT,
  metadata_json TEXT,
  indexed_at TEXT NOT NULL
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  chunk_type TEXT NOT NULL,
  text TEXT NOT NULL,
  timestamp_start REAL,
  timestamp_end REAL,
  metadata_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE bucket_definitions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  bucket_type TEXT,
  is_active INTEGER DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE bucket_rules (
  id TEXT PRIMARY KEY,
  bucket_name TEXT NOT NULL,
  rule_type TEXT NOT NULL,
  pattern TEXT NOT NULL,
  weight REAL DEFAULT 1.0,
  applies_to TEXT,
  is_active INTEGER DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE item_buckets (
  item_id TEXT NOT NULL,
  bucket_name TEXT NOT NULL,
  confidence REAL NOT NULL,
  evidence_json TEXT,
  assigned_by TEXT NOT NULL,
  assigned_at TEXT NOT NULL,
  PRIMARY KEY (item_id, bucket_name)
);

CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  chunk_id TEXT NOT NULL,
  model TEXT NOT NULL,
  embedding_json TEXT NOT NULL,
  dimensions INTEGER,
  created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE chunk_fts USING fts5(
  chunk_id UNINDEXED,
  text
);
```

MVP requirement:

* Store sources, items, chunks, buckets, bucket evidence, embeddings, and FTS text.
* Use SQLite FTS5 for keyword search.
* Store embeddings as JSON at first.

---

### 10. Ollama Embeddings

Ollama should be used to embed chunks, not whole files.

Example chunk-to-embedding flow:

```text
chunk text
   ↓
Ollama /api/embed
   ↓
embedding vector
   ↓
embeddings table
```

MVP requirement:

* Support configurable embedding model.
* Generate one embedding per chunk.
* Skip embedding chunks that already have an embedding for the selected model.
* Allow embeddings to be regenerated if the model changes.

Suggested config:

```yaml
ollama:
  base_url: http://localhost:11434
  embedding_model: nomic-embed-text
```

#### Ollama setup with Vulkan GPU acceleration

Use these steps when the machine needs Ollama to run through the Vulkan backend instead of CUDA/ROCm/CPU. This is useful for many AMD, Intel, and other GPUs that expose Vulkan but are not covered by the native Ollama GPU backends.

1. **Install Ollama** from the official installer for your OS, then confirm the CLI is available:

   ```bash
   ollama --version
   ```

2. **Install a working Vulkan driver/runtime** for the GPU. On Linux, also install `vulkaninfo`/`vulkan-tools` and verify that the GPU is visible:

   ```bash
   vulkaninfo --summary
   ```

3. **Start the Ollama server with Vulkan enabled.** For an interactive shell:

   ```bash
   OLLAMA_VULKAN=1 ollama serve
   ```

   For a systemd service, add the environment variable to the Ollama service override, then restart Ollama:

   ```ini
   [Service]
   Environment="OLLAMA_VULKAN=1"
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart ollama
   ```

4. **Pull the models used by this project.** `nomic-embed-text` is the default embedding model used by `python -m archive_indexer embed`; `llama3.2:1b` is used by the lightweight local LLM embedding helper.

   ```bash
   ollama pull nomic-embed-text
   ollama pull llama3.2:1b
   ```

5. **Smoke-test Ollama before running the indexer.**

   ```bash
   ollama run llama3.2:1b "Say ok"
   ```

6. **Generate embeddings and run semantic search.**

   ```bash
   python -m archive_indexer embed
   python -m archive_indexer search "local ai vector search" --semantic
   ```

If Vulkan is misconfigured, Ollama may fail to load a model or fall back to CPU. Check the Ollama server logs and confirm `OLLAMA_VULKAN=1` is present in the server environment.

Alternative embedding models to try later:

```text
nomic-embed-text
mxbai-embed-large
all-minilm
embeddinggemma
```

---

### 11. Search CLI

The MVP should include a basic command-line search tool.

Example commands:

```bash
python -m archive_indexer search "electrical apprenticeship advice"
python -m archive_indexer search "140 bpm garage loop" --bucket music_production
python -m archive_indexer search "ollama embeddings" --bucket local_ai
python -m archive_indexer show /archive/old_tiktoks/saved/video_8392.mp4
```

MVP search behavior:

1. Run SQLite FTS keyword search.
2. Run embedding similarity search.
3. Merge and rank results.
4. Show path or URL.
5. Show bucket labels.
6. Show matched chunk text.
7. Show timestamp when the match came from video OCR.
8. Show bucket evidence when requested.

Example output:

```text
1. /archive/old_tiktoks/saved/video_8392.mp4
   buckets: tiktok_saved, electrical, career
   matched chunk: frame_ocr at 00:00:10
   text: "how I got into the electrical trade without experience"

2. https://example.com/local-llm-vector-search
   buckets: bookmarks, local_ai
   matched chunk: bookmark_metadata
   title: Local LLM vector search examples
```

---

## Recommended Starting Buckets

### Source Buckets

```text
tiktok_saved
bookmarks
old_downloads
personal_files
```

### Topic Buckets

```text
electrical
local_ai
music_production
career
software_dev
media_reference
memes_or_social
personal_admin
```

### Status Buckets

```text
review_later
important
duplicate_candidate
low_signal
```

---

## Suggested Project Structure

```text
archive-indexer/
  README.md
  pyproject.toml
  config/
    sources.yaml
    buckets.yaml
    settings.yaml
  data/
    archive_index.sqlite
    frame_cache/
  src/
    archive_indexer/
      __init__.py
      cli.py
      db.py
      config.py
      ingest.py
      bucket_rules.py
      search.py
      embed_ollama.py
      extractors/
        __init__.py
        generic_files.py
        audio.py
        video.py
        bookmarks.py
        ocr.py
  tests/
    test_bucket_rules.py
    test_bookmarks.py
    test_db.py
```

---

## Roadmap

## Phase 0: Project Skeleton

Goal: Create the project structure and make sure the CLI runs.

Tasks:

* Create Python package structure.
* Add `pyproject.toml`.
* Add empty CLI entrypoint.
* Add config loading for YAML files.
* Add database connection helper.
* Add basic logging.

Definition of done:

```bash
python -m archive_indexer --help
```

prints available commands.

---

## Phase 1: Database Setup

Goal: Create the SQLite database and schema.

Tasks:

* Implement `init-db` command.
* Create all MVP tables.
* Create FTS5 table.
* Add indexes.
* Add simple migration/version table if desired.

Definition of done:

```bash
python -m archive_indexer init-db
```

creates:

```text
data/archive_index.sqlite
```

with all required tables.

---

## Phase 2: Source and Folder Ingestion

Goal: Scan configured folders and record files as items.

Tasks:

* Read `config/sources.yaml`.
* Insert sources into `sources` table.
* Recursively walk folders.
* Insert file rows into `items`.
* Detect extension and basic media type.
* Skip unchanged files on repeated runs.

Definition of done:

```bash
python -m archive_indexer ingest --source "Old TikToks"
```

adds files to the `items` table.

---

## Phase 3: Basic Chunk Creation

Goal: Create searchable chunks from paths and generic metadata.

Tasks:

* Create `path_metadata` chunk for every file.
* Create `bookmark_metadata` chunk for every bookmark.
* Create `audio_metadata` chunk for audio files.
* Create `video_metadata` chunk for video files.
* Insert chunk text into `chunk_fts`.

Definition of done:

Every ingested item has at least one searchable chunk.

---

## Phase 4: Bookmark Ingestion

Goal: Parse browser bookmark HTML exports.

Tasks:

* Parse bookmark HTML file.
* Extract bookmark title.
* Extract URL.
* Extract domain.
* Extract bookmark folder path.
* Insert bookmark items.
* Create bookmark chunks.

Definition of done:

```bash
python -m archive_indexer ingest-bookmarks config/bookmarks.html
```

adds bookmark items and searchable chunks.

---

## Phase 5: Bucket Rules

Goal: Assign buckets using YAML rules.

Tasks:

* Load `config/buckets.yaml`.
* Insert bucket definitions into database.
* Insert bucket rules into database.
* Evaluate rules against items and chunks.
* Compute confidence scores.
* Store evidence JSON.
* Assign fallback `review_later` bucket if no match is strong enough.

Definition of done:

```bash
python -m archive_indexer assign-buckets
```

creates rows in `item_buckets` with confidence and evidence.

---

## Phase 6: Keyword Search

Goal: Search using SQLite FTS5.

Tasks:

* Implement `search` command.
* Query `chunk_fts`.
* Join chunks to items.
* Show paths/URLs.
* Show matched text.
* Show buckets.
* Support `--bucket` filter.

Definition of done:

```bash
python -m archive_indexer search "electrician advice"
```

returns matching files/bookmarks with useful context.

---

## Phase 7: Ollama Embeddings

Goal: Add semantic search.

Tasks:

* Add Ollama client.
* Read embedding model from config.
* Generate embeddings for chunks.
* Store embeddings in SQLite as JSON.
* Skip already-embedded chunks.
* Implement cosine similarity search.

Definition of done:

```bash
python -m archive_indexer embed
python -m archive_indexer search "stuff about becoming an electrician" --semantic
```

returns semantically similar results even when exact keywords differ.

---

## Phase 8: Video Frame OCR

Goal: Extract text from video frames.

Tasks:

* Use video metadata to determine duration.
* Sample frames every configured number of seconds.
* Cache frames in `data/frame_cache`.
* Run OCR on each sampled frame.
* Store OCR text as `frame_ocr` chunks.
* Add timestamp metadata.
* Insert OCR chunks into FTS and embeddings queue.

Definition of done:

```bash
python -m archive_indexer ocr-videos
```

creates timestamped OCR chunks for videos.

---

## Phase 9: Review and Debug Commands

Goal: Make the system inspectable.

Tasks:

* Show item details.
* Show chunks for an item.
* Show bucket evidence.
* List items in `review_later`.
* List top buckets by item count.
* List files with no chunks.

Example commands:

```bash
python -m archive_indexer show-item /archive/old_tiktoks/saved/video_8392.mp4
python -m archive_indexer explain-buckets /archive/old_tiktoks/saved/video_8392.mp4
python -m archive_indexer list-bucket review_later
python -m archive_indexer bucket-stats
```

Definition of done:

You can answer:

```text
Why did this file get this bucket?
What text was extracted from this file?
Which files need manual review?
```

---

## Phase 10: Polish MVP

Goal: Make it usable on a real messy archive.

Tasks:

* Add progress bars.
* Add dry-run mode.
* Add config validation.
* Add better error handling.
* Add `--limit` options for testing.
* Add `--since` or `--changed-only` mode.
* Add README examples.
* Add small test archive fixture.

Definition of done:

The indexer can be run repeatedly without destroying previous work and without reprocessing unchanged files unnecessarily.

---

## MVP Command List

Target commands:

```bash
python -m archive_indexer init-db
python -m archive_indexer ingest
python -m archive_indexer ingest-bookmarks PATH
python -m archive_indexer assign-buckets
python -m archive_indexer embed
python -m archive_indexer ocr-videos
python -m archive_indexer search "query text"
python -m archive_indexer search "query text" --bucket electrical
python -m archive_indexer search "query text" --semantic
python -m archive_indexer show-item PATH_OR_URL
python -m archive_indexer explain-buckets PATH_OR_URL
python -m archive_indexer list-bucket review_later
python -m archive_indexer bucket-stats
```

---

## MVP Success Criteria

The MVP is successful when it can:

* Scan a folder of mixed old files.
* Parse a bookmark HTML export.
* Extract audio metadata without transcription.
* Extract video metadata.
* Sample video frames and OCR visible text.
* Store all searchable text as chunks.
* Assign configurable buckets with evidence.
* Embed chunks using Ollama.
* Search by keyword.
* Search semantically.
* Filter by bucket.
* Show why a result matched.
* Re-run without duplicating everything.

---

## Later Stretch Goals

Possible features after MVP:

* Small local web UI.
* Thumbnail previews.
* Better duplicate detection.
* Optional webpage fetching for bookmarks.
* Optional Whisper transcription for selected audio/video only.
* Manual tagging interface.
* File move/copy suggestions.
* Export results as CSV or JSON.
* Watch mode for new files.
* Integration with Open WebUI or a local RAG chat interface.
* Switch from JSON embeddings in SQLite to a vector database.
* Add image OCR for screenshots and memes.
* Add perceptual hashing for duplicate images/videos.

---

## Design Principles

### 1. Deterministic First, AI Second

The system should first rely on paths, filenames, metadata, bookmark folders, and OCR. Ollama helps with semantic retrieval, but it should not be the only thing holding the system together.

### 2. Buckets Should Be Debuggable

Every bucket assignment should have evidence.

Good:

```text
Assigned electrical because frame OCR matched "electrician" at 00:00:10.
```

Bad:

```text
Assigned electrical because the AI said so.
```

### 3. Multiple Buckets Are Normal

A single item can be:

```text
tiktok_saved + electrical + career
```

or:

```text
bookmark + local_ai + software_dev
```

Do not force a single category.

### 4. Review Later Is Better Than Wrong

If an item does not match confidently, assign it to:

```text
review_later
```

Then improve rules over time.

### 5. Chunks Are the Search Unit

Search should point to the specific chunk that matched, not just the parent file.

For videos, this means returning timestamps when OCR matched a frame.

---

## First Implementation Target

The first useful version should do this:

```bash
python -m archive_indexer init-db
python -m archive_indexer ingest
python -m archive_indexer assign-buckets
python -m archive_indexer search "ollama embeddings"
```

Then add:

```bash
python -m archive_indexer embed
python -m archive_indexer search "local ai vector search" --semantic
```

Then add video OCR:

```bash
python -m archive_indexer ocr-videos
python -m archive_indexer search "text seen in a saved tiktok"
```

That order gives value quickly without getting blocked on OCR, embeddings, or UI work.

---

## Fake sample input generator

Generate deterministic synthetic files for ingestion, bucket classification, chunking, OCR/caption, and retrieval evaluation:

```bash
make generate-fake-inputs
# or
python scripts/generate_fake_inputs.py
```

Clean generated files:

```bash
make clean-fake-inputs
# or
python scripts/generate_fake_inputs.py --clean
```

Generated output is written to `sample_data/generated/` and is intentionally gitignored. Tiny committed fixtures live in `tests/fixtures/`.

Optional dependencies and fallbacks:

- `reportlab` for richer PDF generation; fallback is deterministic placeholder text with `.pdf` extension.
- `python-docx` for real DOCX files; fallback is deterministic placeholder text with `.docx` extension.
- `ffmpeg` for `.mp3` conversion; fallback is `.wav`.
- Video generation is tool-agnostic with deterministic `.webm` placeholder and deterministic captions.
- `.doc` conversion is optional and not required; generator continues without it.

Use manifests for future evaluation:

- bucket tests: `sample_data/generated/manifests/bucket_expectations.json`
- chunking tests: `sample_data/generated/manifests/chunk_manifest.json`
- retrieval tests: `sample_data/generated/manifests/retrieval_queries.json` + `relevance_judgments.json`

## Future retrieval / needle-in-haystack evaluation

The generated data is structured as a model-agnostic IR benchmark with:

- corpus manifest
- chunk manifest
- bucket expectations
- retrieval queries
- relevance judgments (qrels)
- hard negatives
- evaluation config

This allows testing exact match, filename search, metadata filters, BM25/keyword search, vector search, hybrid search, reranking, OCR search, caption search, and RAG without locking into a specific model, embedding provider, or database.


## Import dependency flow checks (import-linter)

Use `import-linter` to keep module boundaries clean:

```bash
pip install import-linter
lint-imports
```

Suggested dependency flow for this repo:

- `archive_indexer.__main__` → `archive_indexer.cli`
- `archive_indexer.cli` → `archive_indexer.db`, `archive_indexer.config`
- `archive_indexer.db` should not depend on CLI entry modules
- `archive_indexer.config` should stay leaf/simple and avoid importing runtime modules

A starter `.importlinter` config is included at repo root.

## Testing and coverage

This project uses `pytest` with `pytest-cov` and `coverage.py` so test runs report both line and branch coverage.

- **Line coverage** means a line of code executed at least once.
- **Branch coverage** means control-flow outcomes (for example `if` true/false paths) were exercised.
- **Mutation testing** with `mutmut` intentionally changes production code and checks whether tests fail.
- **Surviving mutants** are a signal that code may run during tests but assertions are not strict enough to detect logic changes.

Commands:

```bash
pytest
pytest --cov=src/archive_indexer --cov-branch --cov-report=term-missing:skip-covered
mutmut run
mutmut browse
```

Notes:

- Coverage is useful for finding untested areas, but coverage percentages alone do not prove correctness.
- Mutation testing is slower than normal tests, so run it before merges or for high-value logic rather than every local edit.
- On Windows, `mutmut` may work best inside WSL because it depends on fork-style process behavior.
---

## Logseq Plugin Frontend

Archive Indexer includes a Logseq plugin scaffold at `plugins/logseq-archive-indexer` for browsing the existing Archive Indexer SQLite data from inside Logseq.

The integration is intentionally unidirectional:

```text
Archive Indexer SQLite → snapshot JSON → Logseq plugin → optional Logseq pages
```

The plugin does **not** write back to the Archive Indexer database. It reads a JSON snapshot exported from the existing tables (`sources`, `items`, `chunks`, `item_buckets`, bucket definitions/statistics, and embedding statistics) and lets you browse or selectively import item pages into Logseq.

### Export a snapshot

```bash
python -m archive_indexer export-logseq-snapshot archive-indexer-logseq.json
```

The snapshot omits raw embedding vectors and includes only embedding counts/dimensions so the Logseq frontend stays focused on browsable metadata and text.

### Load the plugin

Install the Logseq plugin SDK dependency first:

```bash
cd plugins/logseq-archive-indexer
npm install
```

Then enable Logseq developer mode, choose **Load unpacked plugin**, and select `plugins/logseq-archive-indexer` directly. Do not select the repository root.

If Logseq reports that the plugin content took too long to load, check that `plugins/logseq-archive-indexer/node_modules/@logseq/libs/dist/lsplugin.user.js` exists, then reload the plugin.
