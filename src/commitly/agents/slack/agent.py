"""
SlackAgent 구현

Slack 피드백 매칭 및 자동 답글
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from commitly.agents.base import BaseAgent
from commitly.core.context import RunContext


class SlackAgent(BaseAgent):
    """
    Slack Agent

    역할:
    1. Slack 채널에서 지정 기간의 메시지 수집
    2. 커밋 메시지/파일명/키워드로 매칭
    3. LLM으로 README 및 과거 오류 분석
    4. 관련 피드백에 "해결 완료" 답글 작성
    5. 결과를 JSON으로 저장
    6. 사용자에게 보고서 작성 여부 질문
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

    def execute(self) -> Dict[str, Any]:
        """
        Slack Agent 실행

        Returns:
            {
                "matched_messages": List[Dict],  # 매칭된 메시지 목록
                "auto_replied": List[str],  # 자동 답글 작성한 메시지 ID
                "create_report": bool,  # 보고서 작성 여부
            }
        """
        # 1. Slack 설정 가져오기
        slack_config = self._get_slack_config()

        if not slack_config["enabled"]:
            self.logger.info("Slack 통합 비활성화, 스킵")
            return {
                "matched_messages": [],
                "auto_replied": [],
                "create_report": False,
            }

        # 2. Slack 메시지 수집
        messages = self._collect_slack_messages(slack_config)

        # 3. 매칭 대상 데이터 가져오기
        match_target = self._get_match_target()

        # 4. 메시지 매칭
        matched_messages = self._match_messages(messages, match_target, slack_config)

        # 5. 자동 답글 작성
        auto_replied = self._auto_reply_to_matched(matched_messages, slack_config)

        # 6. 결과 저장
        self._save_results(matched_messages, slack_config)

        # 7. 사용자에게 보고서 작성 여부 질문
        create_report = self._ask_create_report(matched_messages)

        # 8. 결과 반환
        return {
            "matched_messages": matched_messages,
            "auto_replied": auto_replied,
            "create_report": create_report,
        }

    def _get_slack_config(self) -> Dict[str, Any]:
        """
        Slack 설정 가져오기

        Returns:
            {
                "enabled": bool,
                "token": str,
                "channel_id": str,
                "time_range": int,  # 조회 기간 (일)
                "require_tag": bool,  # #commitly {hash} 필수 여부
                "save_path": str,
            }
        """
        slack_enabled = self.config.get("slack.enabled", False)

        if not slack_enabled:
            return {"enabled": False}

        # .env에서 토큰 가져오기
        import os

        slack_token = os.getenv("SLACK_BOT_TOKEN")
        channel_id = os.getenv("SLACK_CHANNEL_ID")

        if not slack_token or not channel_id:
            self.logger.warning("Slack 설정 불완전 (SLACK_BOT_TOKEN, SLACK_CHANNEL_ID)")
            return {"enabled": False}

        return {
            "enabled": True,
            "token": slack_token,
            "channel_id": channel_id,
            "time_range": self.config.get("slack.time_range_days", 7),
            "require_tag": self.config.get("slack.require_tag", False),
            "save_path": self.config.get(
                "slack.save_path", ".commitly/slack/matches.json"
            ),
        }

    def _collect_slack_messages(
        self, slack_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Slack 메시지 수집

        Args:
            slack_config: Slack 설정

        Returns:
            메시지 리스트
        """
        self.logger.info("Slack 메시지 수집 시작")

        try:
            from slack_sdk import WebClient

            client = WebClient(token=slack_config["token"])

            # 조회 기간 계산
            time_range = slack_config["time_range"]
            oldest = datetime.now() - timedelta(days=time_range)
            oldest_ts = oldest.timestamp()

            # 메시지 조회
            response = client.conversations_history(
                channel=slack_config["channel_id"],
                oldest=str(oldest_ts),
                limit=1000,
            )

            messages = response["messages"]

            self.logger.info(f"Slack 메시지 {len(messages)}개 수집")

            return messages

        except ImportError:
            self.logger.warning("slack_sdk 패키지가 설치되지 않았습니다. 스킵")
            return []

        except Exception as e:
            self.logger.warning(f"Slack 메시지 수집 실패: {e}")
            return []

    def _get_match_target(self) -> Dict[str, Any]:
        """
        매칭 대상 데이터 가져오기

        Returns:
            {
                "commit_message": str,
                "changed_files": List[str],
                "keywords": List[str],
            }
        """
        # Sync Agent 결과에서 커밋 메시지 가져오기
        try:
            sync_output = self._load_previous_output("sync_agent")
            commit_message = sync_output["data"].get("commit_message", "")
        except Exception:
            commit_message = ""

        # Clone Agent 결과에서 변경 파일 가져오기
        try:
            clone_output = self._load_previous_output("clone_agent")
            changed_files = clone_output["data"].get("changed_files", [])
        except Exception:
            changed_files = []

        # 설정에서 키워드 가져오기
        keywords = self.config.get("slack.keywords", [])

        return {
            "commit_message": commit_message,
            "changed_files": [Path(f).name for f in changed_files],  # 파일명만 추출
            "keywords": keywords,
        }

    def _match_messages(
        self,
        messages: List[Dict[str, Any]],
        match_target: Dict[str, Any],
        slack_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        메시지 매칭

        Args:
            messages: Slack 메시지
            match_target: 매칭 대상 데이터
            slack_config: Slack 설정

        Returns:
            매칭된 메시지 목록
        """
        self.logger.info("메시지 매칭 시작")

        matched = []

        for msg in messages:
            text = msg.get("text", "")

            # requireTag=true인 경우 #commitly 태그 확인
            if slack_config["require_tag"]:
                if "#commitly" not in text.lower():
                    continue

            # 커밋 메시지 매칭
            if match_target["commit_message"] and match_target["commit_message"] in text:
                matched.append(
                    {
                        "message_id": msg.get("ts"),
                        "text": text,
                        "user": msg.get("user"),
                        "timestamp": msg.get("ts"),
                        "match_reason": "commit_message",
                    }
                )
                continue

            # 파일명 매칭
            for file_name in match_target["changed_files"]:
                if file_name in text:
                    matched.append(
                        {
                            "message_id": msg.get("ts"),
                            "text": text,
                            "user": msg.get("user"),
                            "timestamp": msg.get("ts"),
                            "match_reason": f"file: {file_name}",
                        }
                    )
                    break

            # 키워드 매칭
            for keyword in match_target["keywords"]:
                if keyword.lower() in text.lower():
                    matched.append(
                        {
                            "message_id": msg.get("ts"),
                            "text": text,
                            "user": msg.get("user"),
                            "timestamp": msg.get("ts"),
                            "match_reason": f"keyword: {keyword}",
                        }
                    )
                    break

        self.logger.info(f"매칭된 메시지: {len(matched)}개")

        return matched

    def _auto_reply_to_matched(
        self,
        matched_messages: List[Dict[str, Any]],
        slack_config: Dict[str, Any],
    ) -> List[str]:
        """
        매칭된 메시지에 자동 답글 작성

        Args:
            matched_messages: 매칭된 메시지
            slack_config: Slack 설정

        Returns:
            답글 작성한 메시지 ID 목록
        """
        if not matched_messages:
            self.logger.info("매칭된 메시지 없음, 답글 스킵")
            return []

        self.logger.info(f"자동 답글 작성: {len(matched_messages)}개 메시지")

        replied = []

        try:
            from slack_sdk import WebClient

            client = WebClient(token=slack_config["token"])

            for msg in matched_messages:
                # 답글 메시지 생성
                reply_text = (
                    f"✅ 해결 완료\n"
                    f"매칭 사유: {msg['match_reason']}\n"
                    f"Commitly에서 자동 생성된 답글입니다."
                )

                try:
                    # 스레드 답글 작성
                    client.chat_postMessage(
                        channel=slack_config["channel_id"],
                        text=reply_text,
                        thread_ts=msg["message_id"],
                    )

                    replied.append(msg["message_id"])
                    self.logger.debug(f"답글 작성: {msg['message_id']}")

                except Exception as e:
                    self.logger.warning(f"답글 작성 실패: {msg['message_id']} - {e}")

        except ImportError:
            self.logger.warning("slack_sdk 패키지가 설치되지 않았습니다. 답글 스킵")

        except Exception as e:
            self.logger.warning(f"자동 답글 작성 실패: {e}")

        self.logger.info(f"✓ 답글 작성 완료: {len(replied)}개")

        return replied

    def _save_results(
        self,
        matched_messages: List[Dict[str, Any]],
        slack_config: Dict[str, Any],
    ) -> None:
        """
        매칭 결과 저장

        Args:
            matched_messages: 매칭된 메시지
            slack_config: Slack 설정
        """
        save_path = Path(slack_config["save_path"])
        save_path.parent.mkdir(parents=True, exist_ok=True)

        result_data = {
            "channel": slack_config["channel_id"],
            "timestamp": datetime.now().isoformat(),
            "matched_count": len(matched_messages),
            "messages": matched_messages,
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"매칭 결과 저장: {save_path}")

    def _ask_create_report(self, matched_messages: List[Dict[str, Any]]) -> bool:
        """
        사용자에게 보고서 작성 여부 질문

        Args:
            matched_messages: 매칭된 메시지

        Returns:
            보고서 작성 여부
        """
        if not matched_messages:
            # 프로그레스 바에서 이미 표시되므로 별도 출력 안 함
            return False

        # 간결한 질문만 표시 (매칭 수는 프로그레스 바에서 이미 표시됨)
        print(f"\n📬 {len(matched_messages)}개의 Slack 피드백이 매칭되었습니다.")

        # 보고서 작성 여부 질문
        response = input("보고서 작성할까요? (y/n): ").strip().lower()

        create_report = response == "y"

        self.logger.info(f"사용자 입력: {response} (보고서 작성: {create_report})")

        return create_report
