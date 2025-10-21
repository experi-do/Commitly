[ Report Agent ]
입력
projectName: 프로젝트 이름
reportPeriod: 보고서 생성 기간
from: 시작일 (예: 2025-10-01T00:00:00+09:00)
to: 종료일 (예: 2025-10-21T23:59:59+09:00)
syncLogPath: Sync Agent 로그 파일 경로
slackMatchPath: Slack Agent 매칭 결과 파일 경로
reportFormat: 보고서 형식 (md, pdf, html)
outputPath: 보고서 파일 저장 경로
filterOption: 보고서 필터 조건
labels: 포함할 라벨 목록 (예: ["hotfix", "backend"])
authors: 포함할 작성자 목록
privacyOption: 개인정보 처리 옵션
anonymizeUser: 이름 익명화 여부 (Boolean)
redactPattern: 마스킹 패턴 리스트 (예: ["password=.*", "api_key=.*"])
기능
syncLogPath, slackMatchPath를 기반으로 기간 내 로그/매칭 결과 로드
각 커밋별 요약 데이터 구성
커밋 메시지 / 파일명
테스트 결과 (Test Agent 결과 연결)
리팩토링 요약 (Refactoring Agent 결과 반영)
Slack 피드백 매칭 결과
filterOption으로 특정 라벨, 작성자, 변경 유형 필터링
privacyOption으로 민감 정보 마스킹 및 이름 익명화
보고서 레이아웃 구성
개요(Overview)
커밋 / 테스트 결과 요약
리팩토링 변경사항
Slack 피드백 및 해결 상태
향후 개선 제안 (LLM 자동 요약)
reportFormat에 맞게 보고서 생성 (Markdown, PDF, HTML)
결과를 outputPath에 저장 후 VS Code 터미널에 완료 로그 출력
Report Agent 종료 → 전체 Flow 종료