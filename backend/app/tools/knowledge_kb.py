"""Embedded vector-store maintenance-manual / past-incident lookup, backed
by Milvus Lite.

Milvus Lite (`pymilvus[milvus_lite]`) runs the vector database in-process
against a local file -- no Docker, no server, no network hop. This mirrors
`langgraph-tutorial-01`'s knowledge-base pattern and
`langgraph-tutorial-05`'s payer-policy-criteria pattern, applied here to
fictitious equipment manuals and past-incident reports (see
`sample-data/manuals/`, `sample-data/incidents/`, and `sample-data/README.md`
for provenance).

IMPORTANT (platform note): Milvus Lite's native binary is published for
Linux and macOS only. It works out of the box inside this repo's Linux
backend Docker image / CI, but will fail to import on native Windows
Python -- run the backend via Docker or WSL on Windows.

IMPORTANT (safety note): the results of `search_plant_knowledge` feed a
root-cause HYPOTHESIS and recommended response for engineer review -- never
an automated diagnosis or equipment-control action. See
`app/graph/nodes.py::investigate_node` and the root README's "Scope &
Safety" section.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.llm import get_embeddings
from app.tools.knowledge_documents import KnowledgeChunk, load_knowledge_chunks

logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_client = None  # lazily-created MilvusClient singleton


@dataclass
class KnowledgeChunkResult:
    chunk_id: str
    doc_type: str
    title: str
    equipment_id: str
    equipment_name: str
    chunk_index: int
    text: str
    score: float


def _get_client():
    """Lazily create (and cache) the Milvus Lite client.

    Lazy + cached so importing this module never requires milvus_lite to be
    installed (unit tests monkeypatch `search_plant_knowledge` directly and
    never call this), and so the file-backed client is opened at most once
    per process.
    """
    global _client
    with _client_lock:
        if _client is None:
            from pymilvus import MilvusClient

            settings = get_settings()
            db_path = Path(settings.milvus_lite_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _client = MilvusClient(str(db_path))
        return _client


def ensure_collection(dim: int = 1536) -> None:
    """Create the plant-knowledge collection if it doesn't already exist."""
    settings = get_settings()
    client = _get_client()
    if not client.has_collection(settings.milvus_collection):
        client.create_collection(
            collection_name=settings.milvus_collection,
            dimension=dim,
            metric_type="COSINE",
            auto_id=False,
        )


def seed_plant_knowledge(force: bool = False) -> int:
    """Embed and upsert every manual/incident paragraph chunk into Milvus
    Lite. Returns the number of chunks (re)inserted. No-op if the
    collection already has data, unless `force=True`."""
    settings = get_settings()
    client = _get_client()

    if client.has_collection(settings.milvus_collection) and not force:
        stats = client.get_collection_stats(settings.milvus_collection)
        if int(stats.get("row_count", 0)) > 0:
            logger.info("Plant knowledge collection already seeded (%s rows); skipping.", stats["row_count"])
            return 0

    chunks: list[KnowledgeChunk] = load_knowledge_chunks(settings.sample_data_dir)

    embeddings = get_embeddings()
    texts = [f"{c.equipment_name} | {c.title} | {c.text}" for c in chunks]
    vectors = embeddings.embed_documents(texts)

    ensure_collection(dim=len(vectors[0]))

    rows = [
        {
            "id": idx,
            "vector": vector,
            "chunk_id": chunk.chunk_id,
            "doc_type": chunk.doc_type,
            "title": chunk.title,
            "equipment_id": chunk.equipment_id,
            "equipment_name": chunk.equipment_name,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
        }
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    client.insert(collection_name=settings.milvus_collection, data=rows)
    logger.info("Seeded %d manual/incident chunks into Milvus Lite.", len(rows))
    return len(rows)


def search_plant_knowledge(
    query: str, equipment_id: str | None = None, top_k: int | None = None
) -> list[KnowledgeChunkResult]:
    """Embed `query` (equipment + anomaly description) and return the
    top-k closest-matching manual/incident paragraphs, optionally filtered
    to a single piece of equipment.

    Returns [] on any failure (e.g. collection not yet seeded, or -- on
    native Windows -- milvus_lite not being installed at all) so the graph
    degrades gracefully to an empty retrieved-context list rather than
    crashing; the engineer reviewing the resulting work order can still
    consult the manuals/incident history manually.
    """
    settings = get_settings()
    k = top_k or settings.knowledge_search_top_k
    try:
        client = _get_client()
        if not client.has_collection(settings.milvus_collection):
            logger.warning("Plant knowledge collection does not exist yet; returning no matches.")
            return []

        embeddings = get_embeddings()
        query_vector = embeddings.embed_query(query)

        filter_expr = f'equipment_id == "{equipment_id}"' if equipment_id else ""

        hits = client.search(
            collection_name=settings.milvus_collection,
            data=[query_vector],
            limit=k,
            filter=filter_expr,
            output_fields=["chunk_id", "doc_type", "title", "equipment_id", "equipment_name", "chunk_index", "text"],
        )
        results: list[KnowledgeChunkResult] = []
        for hit in hits[0]:
            entity = hit.get("entity", hit)
            results.append(
                KnowledgeChunkResult(
                    chunk_id=entity.get("chunk_id", ""),
                    doc_type=entity.get("doc_type", ""),
                    title=entity.get("title", ""),
                    equipment_id=entity.get("equipment_id", ""),
                    equipment_name=entity.get("equipment_name", ""),
                    chunk_index=int(entity.get("chunk_index", 0)),
                    text=entity.get("text", ""),
                    score=float(hit.get("distance", 0.0)),
                )
            )
        return results
    except Exception:  # noqa: BLE001 - deliberate, see docstring
        logger.exception("plant knowledge search failed for query=%r", query)
        return []


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-embed and re-insert even if already seeded.")
    args = parser.parse_args()
    inserted = seed_plant_knowledge(force=args.force)
    print(f"Inserted {inserted} manual/incident chunks into Milvus Lite.")
