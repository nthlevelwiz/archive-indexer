# Archive Indexer Logseq Plugin

A read-only Logseq frontend for Archive Indexer data.

The plugin does not connect to SQLite directly and does not write back to Archive Indexer. The data path is intentionally one-way:

```text
Archive Indexer SQLite → export-logseq-snapshot JSON → Logseq plugin → optional Logseq pages
```

## Install in Logseq

No build step is required. Load this plugin directory in Logseq's developer plugin loader.

## Use

1. Export a snapshot from the Archive Indexer project:

   ```bash
   python -m archive_indexer export-logseq-snapshot archive-indexer-logseq.json
   ```

2. Open the Archive Indexer toolbar button in Logseq.
3. Choose the exported JSON file.
4. Browse and filter indexed items, chunks, buckets, sources, and embedding stats.
5. Use **Import into Logseq** on specific items when you want a Logseq page copy.

Imported pages include `archive-indexer-direction:: archive-indexer-to-logseq` so the source direction remains explicit.
