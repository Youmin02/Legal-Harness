"""Independent reproduction of the KoBLEX paper's own ParSeR baseline.

This package is a deliberately separate implementation from the project's
skill harness (`skills/`, `harness/`, `runtime/local_ollama_executor.py`).
It exists ONLY to reproduce the retrieval-augmented QA method proposed by
the KoBLEX paper itself:

    Lee, Kim, Hwang, Kim, Lee. "KoBLEX: Open Legal Question Answering with
    Multi-hop Reasoning." EMNLP 2025. https://aclanthology.org/2025.emnlp-main.200/

ParSeR = Parametric provision-guided Selection Retrieval, the paper's
proposed method (not the project's own S1/S2/S3 skill-harness method).
Do not import anything from `skills/`, `harness/`, or `runtime/` into this
package, and do not import this package from the skill-harness runtime --
the two pipelines must stay independently runnable and independently
auditable for a fair baseline comparison.

Source of the reference implementation (read, ported, not vendored
verbatim as a git submodule): https://github.com/daehuikim/KoBLEX
  experiments/parser/prompts/*.py
  experiments/parser/vllm/*.py
as of 2026-08-19.

See docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md for the full list of
deliberate deviations from the released reference code (an indexing bug in
the official `selection_retrieval.py` was fixed per the paper's stated
algorithm; see that document for details).
"""
