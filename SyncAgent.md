[ Sync Agent ]
입력
userInput: main 브랜치에 push할지 여부 (CLI에서 y/n 입력)
projectName: 현재 프로젝트 이름
commitMessage: 현재 커밋 메시지 (예: [hotfix] api.py 연결 오류 해결)
commitFileList: 커밋에 포함된 파일 경로 리스트
remoteRepo: 원격 저장소 이름 (예: origin)
remoteBranch: 동기화 대상 브랜치 이름 (예: main)
testResultPath: Test Agent에서 생성된 테스트 결과 파일 경로
기능
사용자의 y/n 입력에 따라 분기
y: 원격 저장소(main)에 push 진행
n: push 생략 후 Slack Agent로 바로 이동
변경된 파일(commitFileList)을 .commitly/hub 기준으로 확인
git diff 결과를 기반으로 변경 로그 계산
원격 저장소에 push (git push origin main)
동기화 결과를 .commitly/logs/ 디렉토리에 JSON으로 저장
저장 JSON 항목
프로젝트명
커밋 메시지
커밋된 파일 리스트
실행된 agent flow ([clone, code, test, refactor, sync])
push 성공 여부
실행 시각 및 로그 ID
push 또는 로그 저장 중 오류 발생 시 사용자에게 경고 후 Sync 종료
오류 없으면 Slack Agent로 이동
