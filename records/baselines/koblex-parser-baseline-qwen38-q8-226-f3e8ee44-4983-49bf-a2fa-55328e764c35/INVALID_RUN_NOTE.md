# Invalid run — preserved for history only, not a baseline result

Stopped after 35/226 items (2026-08-19). The CrossEncoder rerank query in
this run used the parametric-provision text instead of the original
question, which does not match the official KoBLEX ParSeR design (see
`docs/KOBLEX_PARSER_BASELINE_REPRODUCTION_NOTES.md`, "구현 오류 수정"
section). Fixed in commit that follows this one and re-run under a new
batch UUID.

Do not use `final_results.jsonl` in this directory for any reported metric.
