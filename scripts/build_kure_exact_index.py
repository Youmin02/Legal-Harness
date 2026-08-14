#!/usr/bin/env python3
"""Build a resumable exact KURE vector matrix for the KoBLEX statute corpus.

Long statutes can be much more expensive than the common short provision.  To
avoid a single long provision making an otherwise efficient GPU batch fail,
this builder uses length-aware batches and retains ``.tmp`` artifacts on a
failure. Re-running the command resumes exactly after the last written ID.
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Sequence, Tuple

import numpy as np
import pyarrow.parquet as pq
import torch
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = PROJECT_ROOT / "data/koblex/statute/corpus-00000-of-00001.parquet"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/koblex/indexes/kure-v1"
DEFAULT_MODEL = PROJECT_ROOT / "models/huggingface/nlpai-lab--KURE-v1"
DEFAULT_BM25 = PROJECT_ROOT / "data/koblex/indexes/bm25/statute_fts5.sqlite3"
MODEL_ID = "nlpai-lab/KURE-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_provision_id(source_index: str, row_number: int) -> str:
    return "%s#KOBLEX-%06d" % (source_index, row_number)


def source_rows(path: Path, batch_size: int) -> Iterator[List[Tuple[str, str]]]:
    parquet = pq.ParquetFile(path)
    row_number = 0
    for batch in parquet.iter_batches(batch_size=batch_size, columns=["index", "content"]):
        rows: List[Tuple[str, str]] = []
        for row in batch.to_pylist():
            source_index, content = row["index"], row["content"]
            if not isinstance(source_index, str) or not source_index.strip():
                raise ValueError("KoBLEX statute has an invalid provision ID")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("KoBLEX statute has empty provision text")
            row_number += 1
            rows.append((canonical_provision_id(source_index, row_number), content))
        yield rows


def line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def encode_with_fallback(
    model: SentenceTransformer,
    texts: Sequence[str],
    batch_size: int,
) -> np.ndarray:
    """Split a batch recursively only when CUDA reports an OOM condition."""
    try:
        return np.asarray(
            model.encode(
                list(texts),
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )
    except torch.OutOfMemoryError:
        if len(texts) == 1:
            raise
        torch.cuda.empty_cache()
        midpoint = len(texts) // 2
        print("CUDA OOM: splitting a batch of %d texts" % len(texts), flush=True)
        return np.concatenate(
            [
                encode_with_fallback(model, texts[:midpoint], max(1, batch_size // 2)),
                encode_with_fallback(model, texts[midpoint:], max(1, batch_size // 2)),
            ],
            axis=0,
        )


def encode_length_aware(
    model: SentenceTransformer,
    texts: Sequence[str],
    dimension: int,
    normal_batch_size: int,
) -> np.ndarray:
    """Keep long statute texts out of high-throughput batches."""
    result = np.empty((len(texts), dimension), dtype=np.float32)
    tiers = (
        (2500, normal_batch_size),
        (7000, min(8, normal_batch_size)),
        (float("inf"), 1),
    )
    assigned = [False] * len(texts)
    for character_limit, batch_size in tiers:
        positions = [
            index
            for index, text in enumerate(texts)
            if not assigned[index] and len(text) <= character_limit
        ]
        for start in range(0, len(positions), batch_size):
            current_positions = positions[start : start + batch_size]
            current_texts = [texts[index] for index in current_positions]
            embeddings = encode_with_fallback(model, current_texts, batch_size)
            if embeddings.shape != (len(current_positions), dimension):
                raise ValueError("KURE returned an unexpected embedding shape")
            result[current_positions] = embeddings
            for index in current_positions:
                assigned[index] = True
    if not all(assigned):
        raise ValueError("some statute texts were not assigned to an encoding tier")
    return result


def prepare_output(
    vectors_tmp: Path,
    ids_tmp: Path,
    total_rows: int,
    dimension: int,
) -> Tuple[np.memmap, int]:
    vectors_tmp.parent.mkdir(parents=True, exist_ok=True)
    id_count = line_count(ids_tmp)
    if vectors_tmp.exists() and ids_tmp.exists() and id_count:
        vectors = np.load(vectors_tmp, mmap_mode="r+")
        if vectors.shape != (total_rows, dimension) or vectors.dtype != np.float32:
            raise ValueError("partial KURE vector file has an incompatible shape or dtype")
        print("Resuming KURE index after %d statutes" % id_count, flush=True)
        return vectors, id_count
    vectors_tmp.unlink(missing_ok=True)
    ids_tmp.unlink(missing_ok=True)
    vectors = np.lib.format.open_memmap(
        vectors_tmp,
        mode="w+",
        dtype=np.float32,
        shape=(total_rows, dimension),
    )
    return vectors, 0


def build(args: argparse.Namespace) -> Tuple[int, int]:
    total_rows = pq.ParquetFile(args.corpus).metadata.num_rows
    vectors_path = args.output / "vectors.f32.npy"
    ids_path = args.output / "provision_ids.txt"
    vectors_tmp = vectors_path.with_suffix(vectors_path.suffix + ".tmp")
    ids_tmp = ids_path.with_suffix(ids_path.suffix + ".tmp")

    model = SentenceTransformer(str(args.kure_model), device=args.device)
    dimension = model.get_sentence_embedding_dimension()
    if not isinstance(dimension, int) or dimension <= 0:
        raise ValueError("KURE did not report a usable embedding dimension")
    vectors, written = prepare_output(vectors_tmp, ids_tmp, total_rows, dimension)
    if written > total_rows:
        raise ValueError("partial KURE ID file has more rows than the source corpus")

    skipped = written
    handle_mode = "a" if written else "w"
    try:
        with ids_tmp.open(handle_mode, encoding="utf-8") as ids:
            for rows in source_rows(args.corpus, args.parquet_batch_size):
                if skipped >= len(rows):
                    skipped -= len(rows)
                    continue
                if skipped:
                    rows = rows[skipped:]
                    skipped = 0
                texts = [content for _, content in rows]
                embeddings = encode_length_aware(
                    model,
                    texts,
                    dimension,
                    args.normal_batch_size,
                )
                vectors[written : written + len(rows)] = embeddings
                for provision_id, _ in rows:
                    ids.write(provision_id)
                    ids.write("\n")
                written += len(rows)
                if written % 10000 < len(rows):
                    vectors.flush()
                    ids.flush()
                    print("KURE embedded %d/%d statutes" % (written, total_rows), flush=True)
    except Exception:
        vectors.flush()
        del vectors
        print("KURE build stopped; rerun this command to resume from %d statutes" % written, flush=True)
        raise
    vectors.flush()
    del vectors
    if written != total_rows:
        raise ValueError("KURE output count does not match source row count")
    vectors_tmp.replace(vectors_path)
    ids_tmp.replace(ids_path)
    return written, dimension


def validate_and_write_metadata(args: argparse.Namespace, count: int, dimension: int) -> None:
    vectors_path = args.output / "vectors.f32.npy"
    ids_path = args.output / "provision_ids.txt"
    vectors = np.load(vectors_path, mmap_mode="r")
    norms = np.linalg.norm(np.asarray(vectors[: min(1024, count)]), axis=1)
    if vectors.shape != (count, dimension) or not np.allclose(norms, 1.0, rtol=1e-3, atol=1e-3):
        raise ValueError("KURE artifact failed shape or normalization validation")
    if line_count(ids_path) != count:
        raise ValueError("KURE ID mapping count does not match vector count")
    connection = sqlite3.connect(str(args.bm25_index))
    try:
        bm25_count = connection.execute("SELECT COUNT(*) FROM provision_fts").fetchone()[0]
    finally:
        connection.close()
    if bm25_count != count:
        raise ValueError("BM25 and KURE document counts differ")

    metadata_path = args.output.parent / "metadata.json"
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(args.corpus.relative_to(PROJECT_ROOT)),
            "sha256": sha256_file(args.corpus),
            "documents": count,
        },
        "bm25": {
            "path": str(args.bm25_index.relative_to(PROJECT_ROOT)),
            "engine": "SQLite FTS5 bm25",
        },
        "kure": {
            "model_id": MODEL_ID,
            "model_path": str(args.kure_model.relative_to(PROJECT_ROOT)),
            "vectors_path": str(vectors_path.relative_to(PROJECT_ROOT)),
            "provision_ids_path": str(ids_path.relative_to(PROJECT_ROOT)),
            "dimension": dimension,
            "dtype": "float32",
            "distance": "exact cosine via normalized dot product",
            "long_text_batching": {"up_to_2500_characters": args.normal_batch_size, "up_to_7000_characters": 8, "over_7000_characters": 1},
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Validated exact KURE index: documents=%d, shape=%s, mean_norm=%.6f"
        % (count, vectors.shape, float(norms.mean())),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kure-model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--bm25-index", type=Path, default=DEFAULT_BM25)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--normal-batch-size", type=int, default=64)
    parser.add_argument("--parquet-batch-size", type=int, default=2048)
    args = parser.parse_args()
    if not args.corpus.is_file() or not args.kure_model.is_dir() or not args.bm25_index.is_file():
        raise FileNotFoundError("the KoBLEX corpus, local KURE model, and BM25 index are required")
    if args.normal_batch_size < 1 or args.parquet_batch_size < 1:
        raise ValueError("batch sizes must be positive")
    count, dimension = build(args)
    validate_and_write_metadata(args, count, dimension)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("KURE index build failed: %s" % exc, file=sys.stderr)
        raise
