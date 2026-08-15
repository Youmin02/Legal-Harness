# 변경 기록

## 1.0-handoff-split — 2026-08-11

- 단일 인수인계 문서를 연구 작업 단위별 Markdown 12개로 분할했다.
- `00_START_HERE.md`와 `README.md`에 권장 읽기 순서와 문서 지도를 추가했다.
- 원본 전체 문서는 `99_FULL_CANONICAL_SOURCE.md`에 무수정 보존했다.
- `SPLIT_MANIFEST.md`에 원본 절과 분할 파일의 대응 관계 및 SHA-256을 기록했다.
- Figure 1, 설계 근거 PDF, 피겨용 아이콘은 `assets/`에 보존했다.

## 변경 원칙

- 동결 결정, 실행 불변식, 데이터 계약을 바꿀 때는 관련 분할 문서와 `99_FULL_CANONICAL_SOURCE.md`의 후속 버전을 함께 갱신한다.
- `version`, `status`, `last_updated` 메타데이터와 이 변경 기록을 동시에 갱신한다.
- 논문, Notion, Figma, 코드에서 변수명과 action enum을 일치시킨다.
