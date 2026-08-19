"""List-parsing helpers for stage-1 output, ported verbatim from the
official KoBLEX repository's `experiments/parser/vllm/utils.py`
(fetched 2026-08-19 from raw.githubusercontent.com/daehuikim/KoBLEX/main).

Only `escape_quotes` is intentionally NOT applied to the parsed list here.
In the official code, `escape_quotes` manually backslash-escapes quotes in
each parametric-provision string and that already-escaped string is later
passed through `json.dumps(..., ensure_ascii=False)`, which escapes quotes
again -- a double-escaping quirk of the released code. Reproducing it would
inject literal backslashes into the BM25 query text with no benefit to
fidelity, so this baseline keeps the plain parsed strings and lets
`json.dumps` do the (single, correct) escaping when writing JSONL. This
follows the "reproduce the paper's intended algorithm" instruction that also
covers the confirmed `contexts_list[0][choice]` indexing bug in stage 2
(see docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md).
"""

import ast
import json
from typing import List, Optional


def extract_first_list(txt: str) -> Optional[str]:
    """Extract the first list from text that starts with '[' and ends with ']'."""
    start = txt.find("[")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(txt[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return txt[start : i + 1]
    return None


def _fix_common_typos(block: str) -> str:
    """Fix common typos in list blocks."""
    block = block.replace(":]", "]")
    if not block.rstrip().endswith("]"):
        block = block.rstrip(" :;,") + "]"
    if block.count('"') % 2 == 1:
        block = block[:-1] + '"' + block[-1]
    return block


def parse_list_block(block: str) -> List[str]:
    """Parse a list block using multiple parsing strategies."""
    block = _fix_common_typos(block)
    for parser in (json.loads, ast.literal_eval):
        try:
            return list(parser(block))
        except Exception:
            pass
    return quoted_items(block)


def quoted_items(text: str) -> List[str]:
    """Extract quoted items from text."""
    items = []
    buf: List[str] = []
    in_q = False
    qchar = None
    esc = False

    for ch in text:
        if in_q:
            if esc:
                buf.append(ch)
                esc = False
            elif ch == "\\":
                buf.append(ch)
                esc = True
            elif ch == qchar:
                items.append("".join(buf))
                buf.clear()
                in_q = False
            else:
                buf.append(ch)
        else:
            if ch in ('"', "'"):
                in_q = True
                qchar = ch
    return items
