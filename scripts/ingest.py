"""
Run this script to ingest your evaluation report PDFs into Qdrant.

Usage (from the project root):
  cd eio-rag
  python scripts/ingest.py            # upsert mode (safe to re-run)
  python scripts/ingest.py --clean    # wipe collection first, then ingest (recommended for re-ingestion)

Before running:
  1. Place your PDF files in data/pdfs/ (organised by year subfolder)
  2. Ensure data/metadata.yaml has one entry per report
  3. Ensure your .env file has all credentials set
"""

import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from config import config
from ingestion import ingest_all


def wipe_collection():
    """Delete the entire Qdrant collection so re-ingestion starts clean."""
    from qdrant_client import QdrantClient
    client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=60)
    existing = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION in existing:
        print(f"\n🗑️  Deleting collection '{config.QDRANT_COLLECTION}'...")
        client.delete_collection(config.QDRANT_COLLECTION)
        print("   ✓ Deleted. Will be recreated fresh during ingestion.")
    else:
        print(f"\n   Collection '{config.QDRANT_COLLECTION}' does not exist yet — nothing to delete.")


def main():
    clean_mode = "--clean" in sys.argv

    print("\n" + "=" * 60)
    print("UNIDO IEU RAG — Ingestion Pipeline")
    if clean_mode:
        print("MODE: CLEAN RE-INGESTION (wipe + rebuild)")
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
        sys.exit(1)

    if not config.METADATA_FILE.exists():
        print(f"\n❌ Metadata file not found: {config.METADATA_FILE}")
        sys.exit(1)

    pdf_files = list(config.PDF_DIR.rglob("*.pdf"))
    print(f"\n✓ Found {len(pdf_files)} PDF files in {config.PDF_DIR}")
    print(f"✓ Qdrant collection: {config.QDRANT_COLLECTION}")
    print(f"✓ Embedding model:   {config.EMBEDDING_MODEL}")
    print(f"✓ Chunk size:        {config.CHUNK_SIZE} tokens, overlap: {config.CHUNK_OVERLAP}")

    if clean_mode:
        print("\n⚠️  --clean mode will DELETE all existing vectors and rebuild from scratch.")
        print("   This fixes corrupted section labels from a previous ingestion run.")

    confirm = input("\nProceed? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    # Wipe first if requested
    if clean_mode:
        wipe_collection()

    # Run ingestion
    results = ingest_all(config.PDF_DIR, config.METADATA_FILE)

    # Summary
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    succeeded = [r for r in results if r.get("status") == "success"]
    failed = [r for r in results if r.get("status") != "success"]

    print(f"\n✅ Successfully ingested: {len(succeeded)} reports")
    for r in succeeded:
        chunks = r.get("chunk_count", "?")
        secs   = r.get("elapsed_seconds", "?")
        print(f"   • {r['title'][:65]} — {chunks} chunks ({secs}s)")

    if failed:
        print(f"\n❌ Failed: {len(failed)} reports")
        for r in failed:
            print(f"   • {r.get('title', '?')} — {r.get('error', 'unknown error')}")

    # Save log
    log_path = Path(__file__).parent.parent / "data" / "ingestion_log.json"
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📋 Log saved to: {log_path}")
    print("\n🚀 Done. Qdrant is ready — restart the backend to use fresh data.")


if __name__ == "__main__":
    main()
