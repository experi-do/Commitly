# 🤝 Contributing Guide (v2)

3인 협업 프로젝트를 위한 일관된 **개발 · 리뷰 · 배포 규칙**입니다.  
브랜치 전략, 커밋 컨벤션(Gitmoji), 코드 스타일, PR 체크리스트를 반드시 준수해주세요.

---

## 🧱 1) Repository Structure (요약)

| 폴더 | 용도 |
|------|------|
| `agents/` | 개별 에이전트 (탐색 / 보강 / RAG / 평가 / 리포트) |
| `graph/` | 상태 · 그래프 · 실행 · 시각화 (통합 지점) |
| `data/` | 원본 및 정제 데이터 |
| `outputs/` | 보고서, 로그, 그래프 이미지 |
| `docs/` | 설계 문서, 평가표, 템플릿 등 |
> 📘 상세 구조는 `README.md` 참조

---

## 🌿 2) Branch Strategy

| 브랜치 | 용도 | 규칙 |
|--------|------|------|
| `main` | 릴리스 / 발표용 (**보호 브랜치**) | 직접 push 금지, PR만 병합 |
| `dev` | 통합 테스트 브랜치 | 모든 기능 브랜치의 머지 대상 |
| `feat/{이름}` | 개인 / 기능 단위 작업 | 예: `feat/keehoon_graph`, `feat/a_discovery` |

```bash
git switch -c feat/yourname_feature

## 🧩 3) Commit Convention (Gitmoji)
타입	예시	의미
✨ :sparkles: feat:	:sparkles: feat: add ScoringAgent decision rule	기능 추가
🐛 :bug: fix:	:bug: fix: handle empty serp results	버그 수정
📝 :memo: docs:	:memo: docs: write architecture.md (v2)	문서 작성
♻️ :recycle: refactor:	:recycle: refactor: split chunks by label	리팩터링
✅ :white_check_mark: test:	:white_check_mark: test: add chroma search tests	테스트
🚧 :construction: chore:	:construction: chore: add logging config	빌드/설정

커밋 메시지 형식:
:emoji: type: subject
본문에는 변경 이유, 영향, 테스트 결과를 간단히 명시합니다.


