const STORAGE_KEY = "archive-indexer.snapshot.v1";
const state = {
    snapshot: loadSnapshot(),
    query: "",
    bucket: "",
    type: "",
    message: "",
};
function loadSnapshot() {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw)
        return null;
    try {
        return assertSnapshot(JSON.parse(raw));
    }
    catch {
        window.localStorage.removeItem(STORAGE_KEY);
        return null;
    }
}
function assertSnapshot(value) {
    const snapshot = value;
    if (snapshot.format !== "archive-indexer-logseq-snapshot" || !Array.isArray(snapshot.items)) {
        throw new Error("Not an Archive Indexer Logseq snapshot");
    }
    return snapshot;
}
function itemTitle(item) {
    return item.filename || item.path_or_url || item.id;
}
function itemText(item) {
    return [
        itemTitle(item),
        item.path_or_url,
        item.item_type,
        item.extension || "",
        item.mime_type || "",
        item.buckets.map((bucket) => bucket.bucket_name).join(" "),
        item.chunks.map((chunk) => chunk.text).join(" "),
    ].join("\n").toLowerCase();
}
function filteredItems() {
    const snapshot = state.snapshot;
    if (!snapshot)
        return [];
    const query = state.query.trim().toLowerCase();
    return snapshot.items.filter((item) => {
        if (state.type && item.item_type !== state.type)
            return false;
        if (state.bucket && !item.buckets.some((bucket) => bucket.bucket_name === state.bucket))
            return false;
        return !query || itemText(item).includes(query);
    });
}
function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
function escapeMarkdown(value) {
    return (value || "").replace(/\[/g, "\\[").replace(/\]/g, "\\]");
}
function renderItemMarkdown(item) {
    const buckets = item.buckets.map((bucket) => `[[archive/bucket/${bucket.bucket_name}]]`).join(" ") || "none";
    const chunks = item.chunks.slice(0, 8).map((chunk) => {
        const text = chunk.text.replace(/\s+/g, " ").slice(0, 500);
        return `  - ${chunk.chunk_type}: ${escapeMarkdown(text)}`;
    });
    return [
        `archive-indexer-id:: ${item.id}`,
        `archive-indexer-type:: ${item.item_type}`,
        `archive-indexer-source:: ${item.source_id}`,
        `archive-indexer-path:: ${escapeMarkdown(item.path_or_url)}`,
        `archive-indexer-direction:: archive-indexer-to-logseq`,
        "",
        `- Source: ${escapeMarkdown(item.path_or_url)}`,
        `- Type: ${item.item_type}`,
        `- Buckets: ${buckets}`,
        `- Indexed at: ${item.indexed_at}`,
        `- Chunks`,
        ...chunks,
    ].join("\n");
}
async function importItem(item) {
    const pageName = `Archive/${itemTitle(item)}`.replace(/[#[\]]/g, " ").trim();
    await logseq.Editor.createPage(pageName, {
        "archive-indexer-id": item.id,
        "archive-indexer-direction": "archive-indexer-to-logseq",
        "archive-indexer-source": item.source_id,
        "archive-indexer-type": item.item_type,
    }, { redirect: false, createFirstBlock: false });
    await logseq.Editor.appendBlockInPage(pageName, renderItemMarkdown(item), {
        properties: {
            "archive-indexer-imported-at": new Date().toISOString(),
        },
    });
    state.message = `Imported ${pageName}`;
    render();
}
function renderStats(snapshot) {
    const bucketText = snapshot.bucket_stats.slice(0, 6).map((bucket) => `<span class="stat">${escapeHtml(bucket.bucket_name)}: ${bucket.c}</span>`).join("");
    const vectors = snapshot.embedding_stats.reduce((total, row) => total + row.count, 0);
    return `<div class="stats">
    <span class="stat">${snapshot.items.length} items</span>
    <span class="stat">${snapshot.sources.length} sources</span>
    <span class="stat">${vectors} embeddings</span>
    ${bucketText}
  </div>`;
}
function renderReferenceTables(snapshot) {
    const sources = snapshot.sources.map((source) => `<tr><td>${escapeHtml(source.label || source.id)}</td><td>${escapeHtml(source.source_type)}</td><td>${escapeHtml(source.root_path_or_file)}</td></tr>`).join("");
    const buckets = snapshot.bucket_stats.map((bucket) => `<tr><td>${escapeHtml(bucket.bucket_name)}</td><td>${bucket.c}</td></tr>`).join("");
    const embeddings = snapshot.embedding_stats.map((row) => `<tr><td>${escapeHtml(row.model)}</td><td>${row.count}</td><td>${escapeHtml(row.dimensions ?? "")}</td></tr>`).join("");
    return `<section class="reference-tables">
    <details>
      <summary>Sources</summary>
      <table><thead><tr><th>Label</th><th>Type</th><th>Path/File</th></tr></thead><tbody>${sources}</tbody></table>
    </details>
    <details>
      <summary>Buckets</summary>
      <table><thead><tr><th>Bucket</th><th>Items</th></tr></thead><tbody>${buckets}</tbody></table>
    </details>
    <details>
      <summary>Embeddings</summary>
      <table><thead><tr><th>Model</th><th>Chunks</th><th>Dimensions</th></tr></thead><tbody>${embeddings}</tbody></table>
    </details>
  </section>`;
}
function renderItem(item) {
    const bucketTags = item.buckets.map((bucket) => `<span class="tag">${escapeHtml(bucket.bucket_name)}</span>`).join("");
    const preview = item.chunks[0]?.text?.slice(0, 280) || "No chunks captured for this item.";
    return `<article class="item-card" data-item-id="${escapeHtml(item.id)}">
    <h2>${escapeHtml(itemTitle(item))}</h2>
    <p>${escapeHtml(item.path_or_url)}</p>
    <div class="item-meta">
      <span class="tag">${escapeHtml(item.item_type)}</span>
      ${item.extension ? `<span class="tag">${escapeHtml(item.extension)}</span>` : ""}
      ${bucketTags}
    </div>
    <pre class="chunk-preview">${escapeHtml(preview)}</pre>
    <button data-import-item="${escapeHtml(item.id)}">Import into Logseq</button>
  </article>`;
}
function render() {
    const app = document.getElementById("app");
    if (!app)
        return;
    const snapshot = state.snapshot;
    const buckets = snapshot ? Array.from(new Set(snapshot.items.flatMap((item) => item.buckets.map((bucket) => bucket.bucket_name)))).sort() : [];
    const types = snapshot ? Array.from(new Set(snapshot.items.map((item) => item.item_type))).sort() : [];
    const items = filteredItems().slice(0, 50);
    app.innerHTML = `<section class="archive-indexer">
    <header class="header">
      <h1>Archive Indexer</h1>
      <p>Read-only frontend for Archive Indexer snapshots. Data flows one way: Archive Indexer → Logseq.</p>
    </header>
    <section class="toolbar">
      <label>Load snapshot JSON exported by <code>python -m archive_indexer export-logseq-snapshot snapshot.json</code></label>
      <input id="snapshot-file" type="file" accept="application/json,.json" />
      <div class="controls">
        <input id="search" type="search" placeholder="Search items, chunks, buckets" value="${escapeHtml(state.query)}" />
        <select id="type-filter"><option value="">All types</option>${types.map((type) => `<option value="${escapeHtml(type)}" ${state.type === type ? "selected" : ""}>${escapeHtml(type)}</option>`).join("")}</select>
        <select id="bucket-filter"><option value="">All buckets</option>${buckets.map((bucket) => `<option value="${escapeHtml(bucket)}" ${state.bucket === bucket ? "selected" : ""}>${escapeHtml(bucket)}</option>`).join("")}</select>
        <button id="clear" class="secondary">Clear snapshot</button>
      </div>
      ${snapshot ? renderStats(snapshot) : ""}
      ${state.message ? `<p>${escapeHtml(state.message)}</p>` : ""}
    </section>
    ${snapshot ? renderReferenceTables(snapshot) : ""}
    ${snapshot ? `<section class="item-list">${items.map(renderItem).join("")}</section>` : `<section class="empty-state">Export a snapshot from Archive Indexer, then choose the JSON file here.</section>`}
  </section>`;
    bindEvents();
}
function bindEvents() {
    document.getElementById("snapshot-file")?.addEventListener("change", async (event) => {
        const input = event.target;
        const file = input.files?.[0];
        if (!file)
            return;
        try {
            const snapshot = assertSnapshot(JSON.parse(await file.text()));
            state.snapshot = snapshot;
            state.message = `Loaded snapshot generated at ${snapshot.generated_at}`;
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
        }
        catch (error) {
            state.message = error instanceof Error ? error.message : "Could not load snapshot";
        }
        render();
    });
    document.getElementById("search")?.addEventListener("input", (event) => {
        state.query = event.target.value;
        render();
    });
    document.getElementById("type-filter")?.addEventListener("change", (event) => {
        state.type = event.target.value;
        render();
    });
    document.getElementById("bucket-filter")?.addEventListener("change", (event) => {
        state.bucket = event.target.value;
        render();
    });
    document.getElementById("clear")?.addEventListener("click", () => {
        state.snapshot = null;
        state.message = "Snapshot cleared from plugin storage.";
        window.localStorage.removeItem(STORAGE_KEY);
        render();
    });
    document.querySelectorAll("[data-import-item]").forEach((button) => {
        button.addEventListener("click", async () => {
            const item = state.snapshot?.items.find((candidate) => candidate.id === button.dataset.importItem);
            if (item)
                await importItem(item);
        });
    });
}
function main() {
    logseq.setMainUIInlineStyle({
        background: "transparent",
        borderRadius: "12px",
        boxShadow: "0 24px 60px rgb(15 23 42 / 24%)",
        maxHeight: "calc(100vh - 96px)",
        overflow: "auto",
        position: "fixed",
        right: "24px",
        top: "72px",
        width: "min(960px, calc(100vw - 48px))",
        zIndex: 11,
    });
    logseq.App.registerUIItem("toolbar", {
        key: "archive-indexer",
        template: "<a data-on-click=\"toggleArchiveIndexer\" class=\"button\">Archive</a>",
    });
    logseq.provideModel({
        toggleArchiveIndexer() {
            logseq.showMainUI();
        },
    });
    render();
}
logseq.ready(main).catch(console.error);
