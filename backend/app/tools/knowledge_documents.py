"""Parses the fictitious maintenance-manual / past-incident `.txt` files
under `sample-data/manuals/` and `sample-data/incidents/` into individual
paragraph chunks ready to embed into Milvus Lite.

Each file follows a small, deliberately simple format (see
`sample-data/README.md` and any file in `manuals/`/`incidents/` for an
example):

    TITLE: <title>
    EQUIPMENT_ID: <fictitious equipment id>
    EQUIPMENT_NAME: <fictitious equipment name>
    DOC_TYPE: manual | incident

    <one or more paragraphs of body text, blank-line separated>

This keeps the sample documents themselves human-readable plain text (real
provenance a reader can open and check), while still giving the seeding
code a trivial, dependency-free way to turn them into individually
embeddable/citable chunks -- one Milvus row per paragraph, each tagged with
its source title/equipment/doc type for filtered semantic search and
citation.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass


@dataclass
class KnowledgeChunk:
    chunk_id: str  # e.g. "c201-discharge-pressure-response-manual-2"
    doc_type: str  # "manual" | "incident"
    title: str
    equipment_id: str
    equipment_name: str
    chunk_index: int
    text: str


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parse_one(path: str) -> list[KnowledgeChunk]:
    title = ""
    equipment_id = ""
    equipment_name = ""
    doc_type = ""
    body_lines: list[str] = []
    in_body = False

    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if not in_body:
                if stripped.startswith("TITLE:"):
                    title = stripped[len("TITLE:") :].strip()
                    continue
                if stripped.startswith("EQUIPMENT_ID:"):
                    equipment_id = stripped[len("EQUIPMENT_ID:") :].strip()
                    continue
                if stripped.startswith("EQUIPMENT_NAME:"):
                    equipment_name = stripped[len("EQUIPMENT_NAME:") :].strip()
                    continue
                if stripped.startswith("DOC_TYPE:"):
                    doc_type = stripped[len("DOC_TYPE:") :].strip()
                    continue
                if stripped == "" and title and equipment_id and doc_type:
                    in_body = True
                    continue
            else:
                body_lines.append(line)

    if not title or not equipment_id or not doc_type:
        raise ValueError(f"{path}: expected TITLE:, EQUIPMENT_ID:, EQUIPMENT_NAME:, and DOC_TYPE: header lines")

    body = "\n".join(body_lines).strip()
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        raise ValueError(f"{path}: no body paragraphs found")

    slug_base = _slug(title)
    return [
        KnowledgeChunk(
            chunk_id=f"{slug_base}-{doc_type}-{i}",
            doc_type=doc_type,
            title=title,
            equipment_id=equipment_id,
            equipment_name=equipment_name,
            chunk_index=i,
            text=paragraph,
        )
        for i, paragraph in enumerate(paragraphs)
    ]


def load_knowledge_chunks(sample_data_dir: str) -> list[KnowledgeChunk]:
    """Parse every `*.txt` file in `sample-data/manuals/` and
    `sample-data/incidents/` into a flat list of per-paragraph chunks."""
    paths: list[str] = []
    for subdir in ("manuals", "incidents"):
        paths.extend(sorted(glob.glob(os.path.join(sample_data_dir, subdir, "*.txt"))))
    if not paths:
        raise SystemExit(
            f"No manual/incident files found under {sample_data_dir!r} (expected manuals/ and incidents/ subfolders)"
        )

    chunks: list[KnowledgeChunk] = []
    for path in paths:
        chunks.extend(_parse_one(path))
    return chunks
