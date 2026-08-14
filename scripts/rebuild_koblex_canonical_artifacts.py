#!/usr/bin/env python3
"""Build the searchable KoBLEX artifacts without recomputing KURE vectors.

The KoBLEX statute corpus's ``index`` column is a legal reference, not a
globally unique row identifier.  The harness needs a unique provision_id for
stable retrieval and citations, so this script assigns a deterministic ID
based on the source row order while retaining the original legal reference.

It rebuilds:
  * data/koblex/normalized/statute.jsonl
  * data/koblex/indexes/bm25/statute_fts5.sqlite3
  * data/koblex/indexes/kure-v1/provision_ids.txt

The KURE embedding matrix is left untouched because its rows remain aligned
with the source corpus order.  A shape check prevents an accidental mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = PROJECT_ROOT / "data/koblex/statute/corpus-00000-of-00001.parquet"
DEFAULT_NORMALIZED = PROJECT_ROOT / "data/koblex/normalized/statute.jsonl"
DEFAULT_BM25 = PROJECT_ROOT / "data/koblex/indexes/bm25/statute_fts5.sqlite3"
DEFAULT_KURE_IDS = PROJECT_ROOT / "data/koblex/indexes/kure-v1/provision_ids.txt"
DEFAULT_KURE_VECTORS = PROJECT_ROOT / "data/koblex/indexes/kure-v1/vectors.f32.npy"
DEFAULT_METADATA = PROJECT_ROOT / "data/koblex/indexes/metadata.json"


def canonical_provision_id(source_index: str, row_number: int) -> str:
    """Return a reproducible, human-readable unique ID for a corpus row."""
    return f"{source_index}#KOBLEX-{row_number:06d}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_atomically(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def build_artifacts(
    corpus_path: Path,
    normalized_path: Path,
    bm25_path: Path,
    kure_ids_path: Path,
    kure_vectors_path: Path,
    metadata_path: Path,
    batch_size: int,
) -> int:
    if not corpus_path.is_file():
        raise FileNotFoundError(f"KoBLEX statute corpus not found: {corpus_path}")
    if not kure_vectors_path.is_file():
        raise FileNotFoundError(
            "KURE vectors are required for mapping validation. Build embeddings first: "
            f"{kure_vectors_path}"
        )

    for path in (normalized_path, bm25_path, kure_ids_path, metadata_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    table = pq.ParquetFile(corpus_path)
    temporary_root = Path(tempfile.mkdtemp(prefix="koblex-canonical-", dir=metadata_path.parent))
    normalized_tmp = temporary_root / "statute.jsonl"
    bm25_tmp = temporary_root / "statute_fts5.sqlite3"
    kure_ids_tmp = temporary_root / "provision_ids.txt"

    row_number = 0
    connection = sqlite3.connect(bm25_tmp)
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE provision_fts USING fts5("
            "provision_id UNINDEXED, statute_name UNINDEXED, provision_text, tokenize='unicode61'"
            ")"
        )
        with normalized_tmp.open("w", encoding="utf-8") as normalized, kure_ids_tmp.open(
            "w", encoding="utf-8"
        ) as provision_ids:
            for batch in table.iter_batches(batch_size=batch_size, columns=["index", "hierarchy", "content"]):
                columns = batch.to_pydict()
                fts_rows: list[tuple[str, str, str]] = []
                for source_index, hierarchy, content in zip(
                    columns["index"], columns["hierarchy"], columns["content"]
                ):
                    row_number += 1
                    source_index = str(source_index or "unknown")
                    statute_name = str(hierarchy or source_index)
                    provision_text = str(content or "")
                    provision_id = canonical_provision_id(source_index, row_number)
                    normalized.write(
                        json.dumps(
                            {
                                "provision_id": provision_id,
                                "source_index": source_index,
                                "statute_name": statute_name,
                                "provision_text": provision_text,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    provision_ids.write(provision_id + "\n")
                    fts_rows.append((provision_id, statute_name, provision_text))
                connection.executemany(
                    "INSERT INTO provision_fts(provision_id, statute_name, provision_text) VALUES (?, ?, ?)",
                    fts_rows,
                )
        connection.execute("INSERT INTO provision_fts(provision_fts) VALUES ('optimize')")
        connection.commit()
    finally:
        connection.close()

    vectors = np.load(kure_vectors_path, mmap_mode="r")
    if vectors.ndim != 2 or vectors.shape[0] != row_number:
        raise RuntimeError(
            "KURE vector rows do not match source corpus rows: "
            f"vectors={vectors.shape}, corpus={row_number}. Rebuild the KURE index."
        )

    replace_atomically(normalized_tmp, normalized_path)
    replace_atomically(bm25_tmp, bm25_path)
    replace_atomically(kure_ids_tmp, kure_ids_path)
    metadata = {
        "source": "JihyungL/KoBLEX-statute",
        "source_file": str(corpus_path.relative_to(PROJECT_ROOT)),
        "source_sha256": file_sha256(corpus_path),
        "documents": row_number,
        "identity": {
            "provision_id": "{KoBLEX index}#KOBLEX-{one-based source row number}",
            "source_index": "original KoBLEX index value retained in normalized corpus",
        },
        "bm25": {
            "type": "SQLite FTS5",
            "database": str(bm25_path.relative_to(PROJECT_ROOT)),
        },
        "kure": {
            "model": "nlpai-lab/KURE-v1",
            "vector_file": str(kure_vectors_path.relative_to(PROJECT_ROOT)),
            "provision_ids": str(kure_ids_path.relative_to(PROJECT_ROOT)),
            "dimensions": int(vectors.shape[1]),
            "similarity": "exact cosine similarity; float32 memory-mapped matrix",
        },
    }
    metadata_tmp = temporary_root / "metadata.json"
    metadata_tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replace_atomically(metadata_tmp, metadata_path)
    temporary_root.rmdir()
    return row_number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--normalized", type=Path, default=DEFAULT_NORMALIZED)
    parser.add_argument("--bm25", type=Path, default=DEFAULT_BM25)
    parser.add_argument("--kure-ids", type=Path, default=DEFAULT_KURE_IDS)
    parser.add_argument("--kure-vectors", type=Path, default=DEFAULT_KURE_VECTORS)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--batch-size", type=int, default=1_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = build_artifacts(
        args.corpus,
        args.normalized,
        args.bm25,
        args.kure_ids,
        args.kure_vectors,
        args.metadata,
        args.batch_size,
    )
    print(f"Built canonical KoBLEX artifacts for {count:,} provisions.")


if __name__ == "__main__":
    main()
