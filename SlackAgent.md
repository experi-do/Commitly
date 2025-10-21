[ Slack Agent ]
입력
projectName: 현재 프로젝트 이름
slackToken: Slack API 토큰 (.env)
channelID: Slack 채널 ID (고정, .env)
timeRange: 조회 기간
from: 조회 시작 시각 (예: 2025-10-14T00:00:00+09:00)
to: 조회 종료 시각 (예: 2025-10-21T23:59:59+09:00)
matchTarget: 매칭 기준 데이터
commitMessage: Sync Agent의 커밋 메시지
commitFileList: 변경된 파일 목록
keywords: 키워드 리스트 (예: ["hotfix", "DB", "api"])
requireTag: Slack 메시지 내 #commitly {hash} 필수 여부 (Boolean)
savePath: 매칭 결과 저장 경로 (예: .commitly/slack/matches.json)
기능
slackToken을 이용해 channelID의 메시지를 지정 기간(timeRange) 동안 수집
matchTarget(커밋 메시지, 파일명, 키워드)을 기준으로 매칭
readme와 LLM을 이용해
프로젝트의 과거 오류 및 수정 내역을 분석
Slack 피드백 중 관련된 오류 보고를 찾아 “해결 완료” 답글 자동 작성
결과를 JSON 형태로 저장
JSON 예시

{
  "channel": "#dev-review",
  "matchedFiles": ["src/api.py"],
  "feedback": ["DB 커넥션 타임아웃 처리 필요"],
  "timestamp": "2025-10-21T10:31:20+09:00",
  "user": "홍길동"
}
매칭 결과가 없으면 “연관 피드백 없음” 메시지 출력 후 Report Agent로 이동
매칭 결과가 존재하면 콘솔 로그에 요약 출력
사용자에게 CLI로 “보고서 작성(y/n)?” 질문
y: Report Agent 실행
n: Flow 종료
