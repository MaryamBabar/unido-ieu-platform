"""
Run this script to ingest your evaluation report PDFs into Qdrant.

Usage (from the project root):
  cd eio-rag
  python scripts/ingest.py

Before running:
  1. Place your PDF files in data/pdfs/
  2. Fill in data/metadata.yaml with one entry per report
  3. Ensure your .env file has all credentials set

This is a one-time operation per report batch. Running it again on the same
reports will upsert (update) existing vectors — safe to re-run.
"""

import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from config import config
from ingestion import ingest_all


def main():
    print("\n" + "=" * 60)
    print("UNIDO IEU RAG — Ingestion Pipeline")
    print("=" * 60)

    # Validate credentials
    missing = config.validate()
    if missing:
        print(f"\n❌ Missing credentials: {', '.join(missing)}")
        print("   Edit your .env file and try again.")
        sys.exit(1)

    # Check paths
    if not config.PDF_DIR.exists():
        print(f"\n❌ PDF directory not found: {config.PDF_DIR}")
        print("   Create the directory and add your PDF files.")
        sys.exit(1)

    if not config.METADATA_FILE.exists():
        print(f"\n❌ Metadata file not found: {config.METADATA_FILE}")
        print("   Copy data/metadata.yaml.example and fill in your reports.")
        sys.exit(1)

    pdf_files = list(config.PDF_DIR.rglob("*.pdf"))
    print(f"\n✓ Found {len(pdf_files)} PDF files in {config.PDF_DIR} (including subfolders)")
    print(f"✓ Qdrant collection: {config.QDRANT_COLLECTION}")
    print(f"✓ Embedding model: {config.EMBEDDING_MODEL}")
    print(f"✓ Chunk size: {config.CHUNK_SIZE} tokens, overlap: {config.CHUNK_OVERLAP} tokens")

    confirm = input("\nProceed with ingestion? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    # Run ingestion
    results = ingest_all(config.PDF_DIR, config.METADATA_FILE)

    # Print summary
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    succeeded = [r for r in results if r.get("status") == "success"]
    failed = [r for r in results if r.get("status") != "success"]

    print(f"\n✅ Successfully ingested: {len(succeeded)} reports")
    for r in succeeded:
        print(f"   • {r['title'][:60]} — {r['chunk_count']} chunks ({r['elapsed_seconds']}s)")

    if failed:
        print(f"\n❌ Failed: {len(failed)} reports")
        for r in failed:
            print(f"   • {r.get('title', '?')} — {r.get('error', 'unknown error')}")

    # Save results log
    log_path = Path(__file__).parent.parent / "data" / "ingestion_log.json"
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📋 Full log saved to: {log_path}")
    print("\n🚀 Qdrant collection is ready. You can now start the backend and query the system.")


if __name__ == "__main__":
    main()
