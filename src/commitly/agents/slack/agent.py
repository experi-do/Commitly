"""
SlackAgent 구현

Slack 피드백 매칭 및 자동 답글
"""

import json
import os
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
        
        # .env 파일 로드 (환경 변수 우선 확인)
        workspace_path = Path(self.run_context["workspace_path"])
        self._load_env_file(workspace_path)
        
        # Config 로드
        from commitly.core.config import Config
        config_path = workspace_path / "config.yaml"
        self.config = Config(config_path)

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

        # 3. sync_agent.json에서 승인 여부 확인
        user_approved = self._check_sync_approval()
        
        if not user_approved:
            self.logger.info("Push가 승인되지 않아 Slack 답글을 건너뜁니다")
            return {
                "matched_messages": [],
                "auto_replied": [],
                "create_report": False,
            }

        # 4. sync_agent.json에서 키워드 추출
        keywords = self._extract_keywords_from_sync_cache()

        # 5. 매칭 대상 데이터 가져오기
        match_target = self._get_match_target()
        
        # sync_agent.json에서 추출한 키워드가 있으면 우선 사용
        if keywords:
            match_target["keywords"] = keywords
            self.logger.info(f"sync_agent.json에서 키워드 추출: {keywords}")

        # 6. 메시지 매칭
        matched_messages = self._match_messages(messages, match_target, slack_config)

        # 7. 자동 답글 작성
        auto_replied = self._auto_reply_to_matched(matched_messages, slack_config)

        # 8. 결과 저장
        self._save_results(matched_messages, slack_config)

        # 9. 결과 반환 (보고서는 별도 명령어로 생성)
        return {
            "matched_messages": matched_messages,
            "auto_replied": auto_replied,
            "create_report": False,  # 보고서는 'commitly report' 명령어로 별도 생성
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
        
        키워드가 여러 개인 경우 모든 키워드가 포함된 메시지만 매칭

        Args:
            messages: Slack 메시지
            match_target: 매칭 대상 데이터
            slack_config: Slack 설정

        Returns:
            매칭된 메시지 목록
        """
        self.logger.info("메시지 매칭 시작")
        self.logger.info(f"매칭 키워드: {match_target['keywords']}")

        matched = []

        for msg in messages:
            text = msg.get("text", "")

            # requireTag=true인 경우 #commitly 태그 확인
            if slack_config["require_tag"]:
                if "#commitly" not in text.lower():
                    continue

            # 키워드 매칭 (모든 키워드가 포함되어야 함)
            keywords = match_target["keywords"]
            if keywords:
                # 모든 키워드가 메시지에 포함되어 있는지 확인
                all_keywords_found = all(
                    keyword in text for keyword in keywords
                )
                
                if all_keywords_found:
                    matched.append(
                        {
                            "message_id": msg.get("ts"),
                            "text": text,
                            "user": msg.get("user"),
                            "timestamp": msg.get("ts"),
                            "match_reason": f"모든 키워드 매칭: {', '.join(keywords)}",
                        }
                    )
                    self.logger.debug(f"✓ 매칭: {text[:50]}...")
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

        if matched:
            self.logger.info(f"✓ 매칭된 메시지: {len(matched)}개")
        else:
            self.logger.info("❌ 매칭되는 메시지가 없습니다")

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

            # 프로젝트명 추출
            workspace_path = Path(self.run_context["workspace_path"])
            project_name = workspace_path.name

            # 에이전트 요약 생성
            summary_text = self._generate_detailed_summary()

            for msg in matched_messages:
                # 매칭 키워드 추출
                keywords_matched = msg.get("match_reason", "").replace("모든 키워드 매칭: ", "")
                
                # 템플릿 형식의 답글 메시지 생성
                reply_text = self._create_reply_template(
                    project_name=project_name,
                    keywords=keywords_matched,
                    summary=summary_text
                )

                try:
                    # 스레드 답글 작성
                    client.chat_postMessage(
                        channel=slack_config["channel_id"],
                        text=reply_text,
                        thread_ts=msg["message_id"],
                    )

                    replied.append(msg["message_id"])
                    self.logger.info(f"✓ 답글 작성 완료: {msg['message_id']}")
                    self.logger.debug(f"   메시지: {msg['text'][:50]}...")
                    self.logger.debug(f"   사유: {msg['match_reason']}")

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
            print("\n연관 피드백 없음")
            return False

        # 요약 출력
        print("\n" + "=" * 60)
        print(f"📬 Slack 피드백 매칭 결과: {len(matched_messages)}개")
        print("=" * 60)

        for i, msg in enumerate(matched_messages[:5], 1):
            print(f"{i}. {msg['text'][:50]}... (사유: {msg['match_reason']})")

        if len(matched_messages) > 5:
            print(f"... 외 {len(matched_messages) - 5}개")

        print("=" * 60)

        # 보고서 작성 여부 질문
        response = input("\n보고서 작성할까요? (y/n): ").strip().lower()

        create_report = response == "y"

        self.logger.info(f"사용자 입력: {response} (보고서 작성: {create_report})")

        return create_report

    def _load_env_file(self, workspace_path: Path) -> None:
        """
        .env 파일 로드
        
        Args:
            workspace_path: 작업 공간 경로
        """
        env_path = workspace_path / ".env"
        
        if not env_path.exists():
            self.logger.debug(f".env 파일 없음: {env_path}")
            return
        
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    # 빈 줄, 주석, '='가 없는 줄은 스킵
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 이미 환경 변수가 있으면 덮어쓰지 않음 (환경 변수 우선)
                    if key not in os.environ:
                        os.environ[key] = value
                        self.logger.debug(f"환경 변수 로드: {key}")
            
            self.logger.info(f"✓ .env 파일 로드 완료: {env_path}")
            
        except Exception as e:
            self.logger.warning(f".env 파일 로드 실패: {e}")

    def _check_sync_approval(self) -> bool:
        """
        sync_agent.json에서 user_approved 확인
        
        Returns:
            bool: push가 승인되었는지 여부
        """
        try:
            workspace_path = Path(self.run_context["workspace_path"])
            sync_cache_path = workspace_path / ".commitly" / "cache" / "sync_agent.json"
            
            if not sync_cache_path.exists():
                self.logger.debug(f"sync_agent.json 파일 없음: {sync_cache_path}")
                return False
            
            with open(sync_cache_path, 'r', encoding='utf-8') as f:
                sync_data = json.load(f)
            
            user_approved = sync_data.get("data", {}).get("user_approved", False)
            
            self.logger.info(f"Sync 승인 여부: {user_approved}")
            
            return user_approved
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"sync_agent.json 파싱 오류: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"Sync 승인 여부 확인 실패: {e}")
            return False
    
    def _extract_keywords_from_sync_cache(self) -> List[str]:
        """
        sync_agent.json에서 commit_message를 읽어 키워드 추출
        
        commit_message를 ,로 구분하여 키워드 리스트 생성
        예: "DB 트랜잭션 지연 해결2, 홍길동" → ["DB 트랜잭션 지연 해결2", "홍길동"]
        
        Returns:
            List[str]: 추출된 키워드 리스트
        """
        try:
            workspace_path = Path(self.run_context["workspace_path"])
            sync_cache_path = workspace_path / ".commitly" / "cache" / "sync_agent.json"
            
            if not sync_cache_path.exists():
                self.logger.debug(f"sync_agent.json 파일 없음: {sync_cache_path}")
                return []
            
            with open(sync_cache_path, 'r', encoding='utf-8') as f:
                sync_data = json.load(f)
            
            # commit_message 추출
            commit_message = sync_data.get("data", {}).get("commit_message", "")
            
            if not commit_message:
                self.logger.debug("sync_agent.json에 commit_message 없음")
                return []
            
            # ,로 구분하여 키워드 추출
            keywords = [keyword.strip() for keyword in commit_message.split(",")]
            
            # 빈 문자열 제거
            keywords = [kw for kw in keywords if kw]
            
            if keywords:
                self.logger.info(f"✓ sync_agent.json에서 키워드 추출 완료: {keywords}")
            else:
                self.logger.debug("sync_agent.json에서 키워드를 추출하지 못함")
            
            return keywords
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"sync_agent.json 파싱 오류: {e}")
            return []
        except Exception as e:
            self.logger.warning(f"키워드 추출 실패: {e}")
            return []
    
    def _create_reply_template(
        self, 
        project_name: str, 
        keywords: str,
        summary: str
    ) -> str:
        """
        템플릿 형식의 Slack 답글 메시지 생성
        
        Args:
            project_name: 프로젝트명
            keywords: 매칭된 키워드
            summary: 에이전트 실행 요약
        
        Returns:
            str: 템플릿 형식의 답글 메시지
        """
        template = f"""*이슈 해결 완료*

*프로젝트:* `{project_name}`
*이슈:* {keywords}

*처리 결과*
{summary}

*상태:* 해결 완료
*다음 단계:* PR 확인해주세요

_Powered by Commitly_"""
        
        return template
    
    def _generate_detailed_summary(self) -> str:
        """
        모든 에이전트 결과를 상세하게 요약
        
        Returns:
            str: 에이전트 실행 결과 요약 (템플릿 형식)
        """
        try:
            workspace_path = Path(self.run_context["workspace_path"])
            cache_dir = workspace_path / ".commitly" / "cache"
            
            summary_parts = []
            
            # 1. Sync Agent (커밋 메시지)
            sync_summary = self._summarize_sync_agent_detailed(cache_dir)
            if sync_summary:
                summary_parts.append(sync_summary)
            
            # 2. Code Agent (SQL 쿼리 감지)
            code_summary = self._summarize_code_agent_detailed(cache_dir)
            if code_summary:
                summary_parts.append(code_summary)
            
            # 3. Test Agent (SQL 최적화)
            test_summary = self._summarize_test_agent_detailed(cache_dir)
            if test_summary:
                summary_parts.append(test_summary)
            
            # 4. Refactoring Agent (리팩토링)
            refactor_summary = self._summarize_refactoring_agent_detailed(cache_dir)
            if refactor_summary:
                summary_parts.append(refactor_summary)
            
            if not summary_parts:
                return "• 모든 에이전트 정상 실행 완료"
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            self.logger.warning(f"상세 요약 생성 실패: {e}")
            return "• 에이전트 실행 완료"
    
    def _summarize_sync_agent_detailed(self, cache_dir: Path) -> str:
        """Sync Agent 결과 상세 요약"""
        try:
            sync_cache = cache_dir / "sync_agent.json"
            if not sync_cache.exists():
                return ""
            
            with open(sync_cache, 'r', encoding='utf-8') as f:
                data = json.load(f).get("data", {})
            
            commit_msg = data.get("commit_message", "").strip()
            if commit_msg:
                # 첫 줄만 추출 (짧게)
                first_line = commit_msg.split('\n')[0]
                if len(first_line) > 50:
                    first_line = first_line[:47] + "..."
                return f"• 커밋: {first_line}"
            
            return ""
            
        except Exception as e:
            self.logger.debug(f"Sync 요약 실패: {e}")
            return ""
    
    def _summarize_code_agent_detailed(self, cache_dir: Path) -> str:
        """Code Agent 결과 상세 요약"""
        try:
            code_cache = cache_dir / "code_agent.json"
            if not code_cache.exists():
                return ""
            
            with open(code_cache, 'r', encoding='utf-8') as f:
                data = json.load(f).get("data", {})
            
            sql_queries = data.get("sql_queries", [])
            lint_passed = data.get("lint_passed", False)
            type_passed = data.get("type_passed", False)
            
            parts = []
            
            # 정적 검사
            if lint_passed and type_passed:
                parts.append("✓ 정적 검사 통과")
            
            # SQL 쿼리
            if sql_queries:
                parts.append(f"SQL 쿼리 {len(sql_queries)}개 발견")
            
            if parts:
                return f"• 코드 검사: {', '.join(parts)}"
            
            return ""
            
        except Exception as e:
            self.logger.debug(f"Code 요약 실패: {e}")
            return ""
    
    def _summarize_test_agent_detailed(self, cache_dir: Path) -> str:
        """Test Agent 결과 상세 요약"""
        try:
            test_cache = cache_dir / "test_agent.json"
            if not test_cache.exists():
                return ""
            
            with open(test_cache, 'r', encoding='utf-8') as f:
                data = json.load(f).get("data", {})
            
            optimizations = data.get("optimizations", [])
            
            if optimizations:
                optimized_count = len([opt for opt in optimizations if opt.get("applied", False)])
                if optimized_count > 0:
                    return f"• SQL 최적화: {optimized_count}개 쿼리 개선"
            
            return ""
            
        except Exception as e:
            self.logger.debug(f"Test 요약 실패: {e}")
            return ""
    
    def _summarize_refactoring_agent_detailed(self, cache_dir: Path) -> str:
        """Refactoring Agent 결과 상세 요약"""
        try:
            refactor_cache = cache_dir / "refactoring_agent.json"
            if not refactor_cache.exists():
                return ""
            
            with open(refactor_cache, 'r', encoding='utf-8') as f:
                data = json.load(f).get("data", {})
            
            refactored = data.get("refactored_files", [])
            
            if refactored:
                return f"• 리팩토링: {len(refactored)}개 파일 개선"
            
            return ""
            
        except Exception as e:
            self.logger.debug(f"Refactor 요약 실패: {e}")
            return ""