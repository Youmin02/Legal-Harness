"""Minimal, dependency-free Ollama client for the ParSeR baseline.

Independent from `runtime/local_ollama_executor.py` (the skill harness's
executor) by design -- see `baselines/koblex_parser/__init__.py`. This
client does not force JSON output and does not know about the skill
contracts; it just runs free-text completion the way the official ParSeR
`vllm/*.py` scripts do (`tokenizer.apply_chat_template(..., enable_thinking=False)`
then greedy decode), adapted to Ollama's HTTP API.

The Qwen3.8 Ollama alias (`configs/ollama/Qwen3.8-27B-Q8_0.Modelfile`) bakes
in a raw-completion TEMPLATE with only a `{{ .Prompt }}` slot (no system-role
slot), matching the pattern already proven to work for this project's own
S1/S2/S3 skill calls. This client therefore folds the system prompt and the
user instruction into a single flattened prompt and calls `/api/generate`,
mirroring `LocalOllamaSkillExecutor._generate` exactly for connection
handling and error semantics.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class OllamaGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GenerationResult:
    text: str
    latency_seconds: float
    prompt_eval_count: int
    eval_count: int


def generate(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    *,
    temperature: float = 0.0,
    num_ctx: int = 32768,
    endpoint: str = "http://127.0.0.1:11434/api/generate",
    timeout_seconds: int = 600,
    keep_alive: str = "30m",
) -> GenerationResult:
    """Run one greedy completion. Raises OllamaGenerationError on failure."""
    flattened_prompt = "%s\n\n%s" % (system_prompt.strip(), user_prompt)
    request_data = json.dumps(
        {
            "model": model,
            "prompt": flattened_prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OllamaGenerationError("Ollama request failed: %s" % exc) from exc
    latency = time.monotonic() - start
    generated = payload.get("response")
    if not isinstance(generated, str):
        raise OllamaGenerationError("Ollama returned no text response: %r" % payload)
    return GenerationResult(
        text=generated,
        latency_seconds=latency,
        prompt_eval_count=int(payload.get("prompt_eval_count") or 0),
        eval_count=int(payload.get("eval_count") or 0),
    )
