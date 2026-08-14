#!/usr/bin/env python3
"""Build reproducible BM25 and KURE exact-search artifacts from KoBLEX statutes.

The KoBLEX source Parquet remains immutable under ``data/koblex/statute``.
All derived files are intentionally stored under the Git-ignored ``data/``
directory.  The dense index is a normalized float32 matrix, not an ANN index:
query-time dot products therefore implement exact cosine retrieval.
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Sequence, Tuple

import numpy as np
import pyarrow.parquet as pq
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = PROJECT_ROOT / "data/koblex/statute/corpus-00000-of-00001.parquet"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/koblex/indexes"
DEFAULT_NORMALIZED = PROJECT_ROOT / "data/koblex/normalized/statute.jsonl"
DEFAULT_KURE_MODEL = PROJECT_ROOT / "models/huggingface/nlpai-lab--KURE-v1"
KURE_MODEL_ID = "nlpai-lab/KURE-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_provision_id(source_index: str, row_number: int) -> str:
    return "%s#KOBLEX-%06d" % (source_index, row_number)


def corpus_rows(path: Path, batch_size: int) -> Iterator[List[Dict[str, str]]]:
    parquet = pq.ParquetFile(path)
    fields = ["index", "hierarchy", "content"]
    row_number = 0
    for batch in parquet.iter_batches(batch_size=batch_size, columns=fields):
        rows: List[Dict[str, str]] = []
        for row in batch.to_pylist():
            source_index = row["index"]
            hierarchy = row["hierarchy"]
            content = row["content"]
            if not all(isinstance(value, str) and value.strip() for value in (source_index, hierarchy, content)):
                raise ValueError("KoBLEX statute row contains an empty index, hierarchy, or content")
            row_number += 1
            rows.append(
                {
                    "provision_id": canonical_provision_id(source_index, row_number),
                    "source_index": source_index,
                    "statute_name": hierarchy,
                    "provision_text": content,
                }
            )
        yield rows


def replace_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)


def build_bm25_and_normalized_corpus(
    corpus_path: Path,
    bm25_path: Path,
    normalized_path: Path,
    batch_size: int,
) -> int:
    bm25_tmp = bm25_path.with_suffix(bm25_path.suffix + ".tmp")
    normalized_tmp = normalized_path.with_suffix(normalized_path.suffix + ".tmp")
    for temporary in (bm25_tmp, normalized_tmp):
        temporary.unlink(missing_ok=True)
    bm25_tmp.parent.mkdir(parents=True, exist_ok=True)
    normalized_tmp.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(bm25_tmp))
    count = 0
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE VIRTUAL TABLE provision_fts USING fts5(
                provision_id UNINDEXED,
                statute_name,
                provision_text,
                tokenize='unicode61'
            );
            """
        )
        with normalized_tmp.open("w", encoding="utf-8") as normalized:
            for rows in corpus_rows(corpus_path, batch_size):
                connection.executemany(
                    "INSERT INTO provision_fts(provision_id, statute_name, provision_text) VALUES (?, ?, ?)",
                    [
                        (row["provision_id"], row["statute_name"], row["provision_text"])
                        for row in rows
                    ],
                )
                for row in rows:
                    normalized.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                    normalized.write("\n")
                count += len(rows)
                if count % 20000 == 0:
                    print("BM25 indexed %d statutes" % count, flush=True)
        connection.execute("INSERT INTO provision_fts(provision_fts) VALUES ('optimize')")
        connection.commit()
    except Exception:
        connection.close()
        bm25_tmp.unlink(missing_ok=True)
        normalized_tmp.unlink(missing_ok=True)
        raise
    connection.close()
    replace_file(bm25_tmp, bm25_path)
    replace_file(normalized_tmp, normalized_path)
    return count


def build_kure_exact_index(
    corpus_path: Path,
    vectors_path: Path,
    ids_path: Path,
    model_path: Path,
    device: str,
    encode_batch_size: int,
    parquet_batch_size: int,
) -> Tuple[int, int]:
    total_rows = pq.ParquetFile(corpus_path).metadata.num_rows
    vectors_tmp = vectors_path.with_suffix(vectors_path.suffix + ".tmp")
    ids_tmp = ids_path.with_suffix(ids_path.suffix + ".tmp")
    for temporary in (vectors_tmp, ids_tmp):
        temporary.unlink(missing_ok=True)
    vectors_tmp.parent.mkdir(parents=True, exist_ok=True)

    model = SentenceTransformer(str(model_path), device=device)
    dimension = model.get_sentence_embedding_dimension()
    if not isinstance(dimension, int) or dimension <= 0:
        raise ValueError("KURE did not report a valid embedding dimension")

    vectors = np.lib.format.open_memmap(
        vectors_tmp,
        mode="w+",
        dtype=np.float32,
        shape=(total_rows, dimension),
    )
    count = 0
    try:
        with ids_tmp.open("w", encoding="utf-8") as ids:
            for rows in corpus_rows(corpus_path, parquet_batch_size):
                texts = [row["provision_text"] for row in rows]
                embeddings = model.encode(
                    texts,
                    batch_size=encode_batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                embeddings = np.asarray(embeddings, dtype=np.float32)
                if embeddings.shape != (len(rows), dimension):
                    raise ValueError("KURE returned an unexpected embedding shape")
                vectors[count : count + len(rows)] = embeddings
                for row in rows:
                    ids.write(row["provision_id"])
                    ids.write("\n")
                count += len(rows)
                if count % 10000 == 0:
                    print("KURE embedded %d/%d statutes" % (count, total_rows), flush=True)
        vectors.flush()
    except Exception:
        del vectors
        vectors_tmp.unlink(missing_ok=True)
        ids_tmp.unlink(missing_ok=True)
        raise
    del vectors
    if count != total_rows:
        raise ValueError("KURE vector count differs from Parquet row count")
    replace_file(vectors_tmp, vectors_path)
    replace_file(ids_tmp, ids_path)
    return count, dimension


def validate_artifacts(
    bm25_path: Path,
    vectors_path: Path,
    ids_path: Path,
    expected_count: int,
    expected_dimension: int,
) -> None:
    connection = sqlite3.connect(str(bm25_path))
    try:
        bm25_count = connection.execute("SELECT COUNT(*) FROM provision_fts").fetchone()[0]
        probe = connection.execute(
            "SELECT provision_id FROM provision_fts WHERE provision_fts MATCH ? LIMIT 1",
            ("법률",),
        ).fetchone()
    finally:
        connection.close()
    vectors = np.load(vectors_path, mmap_mode="r")
    with ids_path.open("r", encoding="utf-8") as handle:
        id_count = sum(1 for _ in handle)
    if bm25_count != expected_count or id_count != expected_count:
        raise ValueError("BM25/vector ID count does not match the source corpus")
    if vectors.shape != (expected_count, expected_dimension):
        raise ValueError("KURE vector matrix has an unexpected shape")
    if probe is None:
        raise ValueError("BM25 smoke query returned no statute")
    norms = np.linalg.norm(np.asarray(vectors[: min(1024, expected_count)]), axis=1)
    if not np.allclose(norms, 1.0, rtol=1e-3, atol=1e-3):
        raise ValueError("KURE embeddings are not normalized for cosine search")
    print(
        "Validated BM25=%d documents, KURE=%s, ids=%d, sample_norm=%.6f"
        % (bm25_count, vectors.shape, id_count, float(norms.mean())),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--normalized-corpus", type=Path, default=DEFAULT_NORMALIZED)
    parser.add_argument("--kure-model", type=Path, default=DEFAULT_KURE_MODEL)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--encode-batch-size", type=int, default=64)
    parser.add_argument("--parquet-batch-size", type=int, default=2048)
    args = parser.parse_args()

    if not args.corpus.is_file():
        raise FileNotFoundError("KoBLEX statute corpus is missing: %s" % args.corpus)
    if not args.kure_model.is_dir():
        raise FileNotFoundError("local KURE model is missing: %s" % args.kure_model)
    if args.encode_batch_size < 1 or args.parquet_batch_size < 1:
        raise ValueError("batch sizes must be positive")

    bm25_path = args.output / "bm25/statute_fts5.sqlite3"
    vectors_path = args.output / "kure-v1/vectors.f32.npy"
    ids_path = args.output / "kure-v1/provision_ids.txt"
    metadata_path = args.output / "metadata.json"

    print("Building BM25 FTS5 index and normalized corpus", flush=True)
    row_count = build_bm25_and_normalized_corpus(
        args.corpus,
        bm25_path,
        args.normalized_corpus,
        args.parquet_batch_size,
    )
    print("Building KURE exact-vector index", flush=True)
    vector_count, dimension = build_kure_exact_index(
        args.corpus,
        vectors_path,
        ids_path,
        args.kure_model,
        args.device,
        args.encode_batch_size,
        args.parquet_batch_size,
    )
    if vector_count != row_count:
        raise ValueError("BM25 and KURE source row counts differ")
    validate_artifacts(bm25_path, vectors_path, ids_path, row_count, dimension)

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(args.corpus.relative_to(PROJECT_ROOT)),
            "sha256": sha256_file(args.corpus),
            "documents": row_count,
        },
        "normalized_corpus": str(args.normalized_corpus.relative_to(PROJECT_ROOT)),
        "bm25": {
            "path": str(bm25_path.relative_to(PROJECT_ROOT)),
            "engine": "SQLite FTS5 bm25",
            "tokenizer": "unicode61",
        },
        "kure": {
            "model_id": KURE_MODEL_ID,
            "local_model_path": str(args.kure_model.relative_to(PROJECT_ROOT)),
            "vectors_path": str(vectors_path.relative_to(PROJECT_ROOT)),
            "provision_ids_path": str(ids_path.relative_to(PROJECT_ROOT)),
            "dimension": dimension,
            "distance": "exact cosine via normalized dot product",
            "dtype": "float32",
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Wrote metadata to %s" % metadata_path, flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("index build failed: %s" % exc, file=sys.stderr)
        raise
