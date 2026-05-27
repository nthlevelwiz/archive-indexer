#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os, shutil, subprocess, wave, struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEED = 1337
CREATED_AT = "2026-01-01T00:00:00Z"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample_data" / "generated"


def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


def clean() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_txt_documents(items, chunks):
    docs = [
        ("doc_fake_school_homework_001", "fake_school_homework_001.txt", ["school_homework"], ["school_homework", "project_notes"], None, False),
        ("doc_fake_ambiguous_lecture_project_notes_001", "fake_ambiguous_lecture_project_notes_001.txt", ["lecture", "project_notes"], ["lecture", "project_notes", "ambiguous"], "Looks like lecture transcript and project notes.", False),
        ("doc_fake_control_generic_note_001", "fake_control_generic_note_001.txt", ["unknown"], ["unknown", "ambiguous"], None, True),
    ]
    for item_id, fn, expected, acceptable, ambiguity, is_control in docs:
        text = f"""TITLE: {fn}\nDATE: 2026-01-01\nTAGS: fake, deterministic, safe\n\nSECTION: Assignment Instructions\nThis section describes a fake homework problem and instructions.\n\nSECTION: Worked Calculation\nThis section contains fake step-by-step calculations and result checks.\n\nSECTION: Citation Notes\nThis section contains fake references and source notes.\n\nSECTION: Reflection\nThis section contains a short synthetic summary.\n"""
        p = OUT / "documents" / fn
        write_text(p, text)
        meta = {
            "id": item_id, "filename": fn, "created_at": CREATED_AT, "source": "generated",
            "expected_buckets": expected, "acceptable_buckets": acceptable,
            "secondary_bucket_candidates": ["project_notes"], "ambiguity_reason": ambiguity,
            "is_control_case": is_control, "bucket_test_reason": "Synthetic deterministic bucket test case.",
            "expected_chunk_topics": ["assignment instructions", "worked calculation", "citation notes"],
            "expected_chunks": [
                {"chunk_id": f"{item_id}_chunk_001", "heading": "Assignment Instructions", "expected_keywords": ["homework", "problem", "instructions"]},
                {"chunk_id": f"{item_id}_chunk_002", "heading": "Worked Calculation", "expected_keywords": ["calculation", "result"]},
            ],
        }
        write_json(OUT / "metadata" / f"{item_id}.metadata.json", meta)
        items.append({"item_id": item_id, "path": str(p.relative_to(ROOT)), "file_type": "txt", "title": fn, "created_at": CREATED_AT, "source": "generated", "expected_buckets": expected, "acceptable_buckets": acceptable, "synthetic_content_description": "Fake text document.", "safe_to_commit": False, "generated_locally": True})
        chunks += [{"chunk_id":f"{item_id}_chunk_001","item_id":item_id,"chunk_type":"document_section","heading":"Assignment Instructions","text":"fake homework problem instructions","expected_keywords":["homework","instructions"],"expected_bucket_signals":expected},{"chunk_id":f"{item_id}_chunk_002","item_id":item_id,"chunk_type":"document_section","heading":"Worked Calculation","text":"step-by-step calculations result","expected_keywords":["calculation","result"],"expected_bucket_signals":expected}]


def generate_pdf_docx(items, chunks):
    reportlab = _safe_import("reportlab")
    docx_mod = _safe_import("docx")
    pdfs = [("doc_fake_project_notes_001", "fake_project_notes_001.pdf", ["project_notes"]), ("doc_fake_receipt_school_supplies_001", "fake_receipt_school_supplies_001.pdf", ["receipt", "school_homework"])]
    for item_id, fn, expected in pdfs:
        p = OUT / "documents" / fn
        if reportlab:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            p.parent.mkdir(parents=True, exist_ok=True)
            c = canvas.Canvas(str(p), pagesize=letter)
            c.drawString(72, 750, "TITLE: Fake PDF")
            c.drawString(72, 730, "SECTION: Assignment Instructions")
            c.drawString(72, 710, "Simple deterministic row: item qty price")
            c.save()
        else:
            write_text(p, "PDF generation unavailable; deterministic placeholder with .pdf extension.")
        items.append({"item_id": item_id, "path": str(p.relative_to(ROOT)), "file_type": "pdf", "title": fn, "created_at": CREATED_AT, "source": "generated", "expected_buckets": expected, "acceptable_buckets": expected+ ["unknown"], "synthetic_content_description": "Fake pdf.", "safe_to_commit": False, "generated_locally": True})
        chunks.append({"chunk_id":f"{item_id}_page_001","item_id":item_id,"chunk_type":"pdf_page","page_number":1,"text":"TITLE Fake PDF SECTION Assignment Instructions","expected_keywords":["assignment","instructions"],"expected_bucket_signals":expected})

    item_id, fn = "doc_fake_legal_notice_001", "fake_legal_notice_001.docx"
    p = OUT / "documents" / fn
    if docx_mod:
        d = docx_mod.Document(); d.add_heading("TITLE: Fake Legal Notice", 0); d.add_paragraph("SECTION: Citation Notes\nThis is synthetic legal-like text."); d.save(str(p))
    else:
        write_text(p, "DOCX generation unavailable placeholder")
    items.append({"item_id": item_id, "path": str(p.relative_to(ROOT)), "file_type": "docx", "title": fn, "created_at": CREATED_AT, "source": "generated", "expected_buckets": ["legal_document"], "acceptable_buckets": ["legal_document", "unknown"], "synthetic_content_description": "Fake docx.", "safe_to_commit": False, "generated_locally": True})
    chunks.append({"chunk_id":f"{item_id}_heading_001","item_id":item_id,"chunk_type":"docx_heading_section","heading":"Citation Notes","text":"synthetic legal notice section","expected_keywords":["legal","notice"],"expected_bucket_signals":["legal_document"]})


def generate_audio(items, chunks):
    sr=16000; duration=4; frames=[]
    for i in range(sr*duration):
        v=int(24000*math.sin(2*math.pi*440*i/sr)); frames.append(struct.pack('<h',v))
    wav = OUT/"audio"/"fake_audio_voice_note_001.wav"; wav.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(wav),'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(b''.join(frames))
    mp3_ok=False
    if shutil.which("ffmpeg"):
        mp3 = OUT/"audio"/"fake_audio_music_loop_001.mp3"
        r=subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(wav),str(mp3)],capture_output=True)
        mp3_ok=r.returncode==0
    if not mp3_ok:
        mp3 = OUT/"audio"/"fake_audio_music_loop_001.wav"
        shutil.copy2(wav, mp3)
    for item_id, fp, expected, speaker in [("audio_fake_voice_note_001", wav, ["voice_note"], "Fake Speaker A"), ("audio_fake_music_loop_001", mp3, ["music", "voice_note"], "Fake Artist Loop")]:
        meta={"id":item_id,"filename":fp.name,"duration_seconds":duration,"title":fp.stem,"fake_artist_or_speaker":speaker,"source":"generated","expected_buckets":expected,"acceptable_buckets":expected+["unknown"],"bucket_test_reason":"Synthetic audio metadata test.","expected_metadata_fields":["duration_seconds","title","source"],"created_at":CREATED_AT}
        write_json(OUT/"audio"/f"{fp.stem}.metadata.json",meta)
        items.append({"item_id":item_id,"path":str(fp.relative_to(ROOT)),"file_type":fp.suffix.lstrip('.'),"title":fp.name,"created_at":CREATED_AT,"source":"generated","expected_buckets":expected,"acceptable_buckets":expected+["unknown"],"synthetic_content_description":"Synthetic audio.","safe_to_commit":False,"generated_locally":True})
        chunks.append({"chunk_id":f"{item_id}_meta_001","item_id":item_id,"chunk_type":"audio_metadata","text":json.dumps(meta),"expected_keywords":["generated","duration_seconds"],"expected_bucket_signals":expected})

def generate_video_and_captions(items, chunks):
    # fallback simple binary placeholder video
    vid=OUT/"video"/"fake_video_local_llm_setup_001.webm"; vid.parent.mkdir(parents=True,exist_ok=True)
    vid.write_bytes(b"FAKEWEBM")
    srt="""1\n00:00:00,000 --> 00:00:02,000\nThis is a fake generated test video.\n\n2\n00:00:02,000 --> 00:00:04,000\nThe visible frame text should be detected by OCR.\n\n3\n00:00:04,000 --> 00:00:06,000\nThis clip explains a fake local LLM setup workflow.\n"""
    vtt="""WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nThis is a fake generated test video.\n\n00:00:02.000 --> 00:00:04.000\nThe visible frame text should be detected by OCR.\n"""
    write_text(OUT/"video"/"fake_video_local_llm_setup_001.srt", srt)
    write_text(OUT/"video"/"fake_video_local_llm_setup_001.vtt", vtt)
    item_id="video_fake_local_llm_setup_001"
    meta={"id":item_id,"filename":vid.name,"duration_seconds":6,"has_captions":True,"caption_files":["fake_video_local_llm_setup_001.srt","fake_video_local_llm_setup_001.vtt"],"expected_ocr_text":["FAKE VIDEO TEST","Bucket: tutorial","Topic: Local LLM Setup","Step 1: Install dependencies","Step 2: Run ingestion"],"expected_caption_chunks":["fake generated test video","detected by OCR"],"expected_buckets":["tutorial","saved_social_video"],"acceptable_buckets":["tutorial","saved_social_video","unknown"],"ambiguity_reason":"tutorial language and short-form video style.","expected_chunk_topics":["local llm setup"],"created_at":CREATED_AT}
    write_json(OUT/"video"/f"{item_id}.metadata.json",meta)
    items.append({"item_id":item_id,"path":str(vid.relative_to(ROOT)),"file_type":"webm","title":vid.name,"created_at":CREATED_AT,"source":"generated","expected_buckets":meta["expected_buckets"],"acceptable_buckets":meta["acceptable_buckets"],"synthetic_content_description":"Synthetic video placeholder with captions and OCR ground truth.","safe_to_commit":False,"generated_locally":True})
    chunks += [{"chunk_id":f"{item_id}_caption_001","item_id":item_id,"chunk_type":"caption_segment","start_seconds":0,"end_seconds":2,"text":"This is a fake generated test video.","expected_keywords":["fake","video"],"expected_bucket_signals":["tutorial"]},{"chunk_id":f"{item_id}_ocr_frame_003","item_id":item_id,"chunk_type":"video_frame_ocr","start_seconds":3,"end_seconds":3,"text":"Step 1: Install dependencies","expected_keywords":["Install","dependencies"],"expected_bucket_signals":["tutorial"]}]


def write_manifests(items, chunks):
    m=OUT/"manifests"; m.mkdir(parents=True, exist_ok=True)
    write_json(m/"corpus_manifest.json", items)
    write_json(m/"chunk_manifest.json", chunks)
    bucket=[{"item_id":i["item_id"],"expected_buckets":i["expected_buckets"],"acceptable_buckets":i["acceptable_buckets"],"secondary_bucket_candidates":["project_notes"],"is_control_case":"control" in i["item_id"],"bucket_test_reason":"Synthetic"} for i in items]
    write_json(m/"bucket_expectations.json", bucket)
    queries=[{"query_id":"q_local_llm_setup_001","query":"find the short video that explains setting up a local LLM","query_type":"semantic_paraphrase","target_bucket":"tutorial","expected_modalities":["video","captions","ocr"],"notes":"Should match the generated video."},{"query_id":"q_homework_calc_001","query":"worked calculation homework notes","query_type":"exact_keyword","target_bucket":"school_homework","expected_modalities":["documents"]}]
    write_json(m/"retrieval_queries.json", queries)
    qrels=[{"query_id":"q_local_llm_setup_001","judgments":[{"target_type":"file","item_id":"video_fake_local_llm_setup_001","relevance":3,"reason":"Exact target."},{"target_type":"caption_chunk","chunk_id":"video_fake_local_llm_setup_001_caption_001","relevance":3,"reason":"Core caption."},{"target_type":"ocr_chunk","chunk_id":"video_fake_local_llm_setup_001_ocr_frame_003","relevance":2,"reason":"frame step text."}]},{"query_id":"q_homework_calc_001","judgments":[{"target_type":"file","item_id":"doc_fake_school_homework_001","relevance":3,"reason":"homework file."}]}]
    write_json(m/"relevance_judgments.json", qrels)
    write_json(m/"hard_negatives.json", [{"query_id":"q_local_llm_setup_001","hard_negatives":[{"target_type":"file","item_id":"doc_fake_project_notes_001","reason":"setup language but not local llm video"}]}])
    write_json(m/"evaluation_config.json", {"metrics":["recall@1","recall@5","recall@10","precision@5","hit_rate@5","mrr","map","ndcg@10"],"retrieval_target_levels":["file","chunk","page","caption_segment","ocr_frame","metadata_field"],"baseline_retrievers_to_support_later":["exact_match","keyword_bm25","metadata_filter","vector_search","hybrid_search","reranker"]})


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--clean", action="store_true"); args=ap.parse_args()
    if args.clean: clean(); return
    clean(); items=[]; chunks=[]
    generate_txt_documents(items, chunks)
    generate_pdf_docx(items, chunks)
    generate_audio(items, chunks)
    generate_video_and_captions(items, chunks)
    write_manifests(items, chunks)

if __name__=="__main__": main()
