import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "scripts" / "generate_fake_inputs.py"
OUT = ROOT / "sample_data" / "generated"


def loadj(p):
    return json.loads(p.read_text())


def test_generator_and_manifests():
    subprocess.run(["python", str(GEN)], check=True)
    assert (OUT / "documents").exists()
    manifests = OUT / "manifests"
    for f in ["corpus_manifest.json", "chunk_manifest.json", "bucket_expectations.json", "retrieval_queries.json", "relevance_judgments.json", "hard_negatives.json", "evaluation_config.json"]:
        assert (manifests / f).exists()

    corpus = loadj(manifests / "corpus_manifest.json")
    chunks = loadj(manifests / "chunk_manifest.json")
    q = loadj(manifests / "retrieval_queries.json")
    rel = loadj(manifests / "relevance_judgments.json")
    hn = loadj(manifests / "hard_negatives.json")

    files = [Path(i["path"]) for i in corpus]
    for p in files:
        assert (ROOT / p).exists()

    item_ids = {i["item_id"] for i in corpus}
    for c in chunks:
        assert c["item_id"] in item_ids

    rmap = {x["query_id"]: x["judgments"] for x in rel}
    for qq in q:
        assert qq["query_id"] in rmap and len(rmap[qq["query_id"]]) >= 1
    for jlist in rmap.values():
        for j in jlist:
            assert j["relevance"] in {0,1,2,3}

    chunk_ids = {c["chunk_id"] for c in chunks}
    for entry in hn:
        for neg in entry["hard_negatives"]:
            if neg["target_type"] == "file":
                assert neg["item_id"] in item_ids
            else:
                assert neg["chunk_id"] in chunk_ids

    txt = (OUT / "documents" / "fake_school_homework_001.txt").read_text()
    assert "SECTION: Assignment Instructions" in txt
    srt = (OUT / "video" / "fake_video_local_llm_setup_001.srt").read_text()
    assert "-->" in srt

    meta = loadj(OUT / "metadata" / "doc_fake_school_homework_001.metadata.json")
    assert "expected_buckets" in meta and "expected_chunks" in meta
