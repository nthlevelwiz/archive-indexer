# Archive Indexer Logseq Plugin (Experimental)

The recommended Logseq integration is now the Python-only Markdown exporter:

```bash
python -m archive_indexer export-logseq-graph ./logseq-archive-indexer
```

Open `./logseq-archive-indexer` as a Logseq graph. This avoids the Logseq plugin runtime and the “content took too long to load” failure path entirely.

The old plugin scaffold remains here only as an experimental JSON browser. It does not connect to SQLite directly and does not write back to Archive Indexer:

```text
Archive Indexer SQLite → export-logseq-snapshot JSON → Logseq plugin → optional Logseq pages
```

If you still want to try the experimental plugin, install the Logseq plugin SDK dependency before loading the unpacked plugin:

```bash
cd plugins/logseq-archive-indexer
npm install
```

Then open Logseq, enable developer mode, choose **Load unpacked plugin**, and select this `plugins/logseq-archive-indexer` directory. Loading the repository root will not work.

If Logseq says the plugin content took too long to load, use the Python Markdown export instead of debugging the plugin loader unless you specifically need the experimental JSON browser.
