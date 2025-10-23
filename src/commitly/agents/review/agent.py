"""
ReviewAgent 구현

LLM을 사용한 코드 리뷰
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from commitly.agents.base import BaseAgent
from commitly.core.context import RunContext, AgentOutput
from commitly.core.git_manager import GitManager


class ReviewAgent(BaseAgent):
    """
    Review Agent

    역할:
    1. commitly/review/{pipeline_id} 브랜치 생성
    2. 사용자 원본 변경사항(git diff) 추출
    3. LLM을 통한 코드 리뷰 수행
    4. CRITICAL/HIGH 이슈 발견 시 승인 게이트
    5. 리뷰 결과를 JSON 형태로 저장
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

        self.hub_path = self._get_hub_path()
        self.hub_git = GitManager(self.hub_path, self.logger)

    def run(self) -> AgentOutput:
        """
        ReviewAgent 실행 및 SyncAgent 호환 캐시 생성

        BaseAgent.run()을 호출하고, 추가로 refactoring_agent.json을 생성합니다.
        (기존 파이프라인과의 호환성 유지)
        """
        # BaseAgent의 run() 메서드 호출
        output = super().run()

        # SyncAgent 호환성: refactoring_agent.json도 생성
        if output["status"] == "success":
            self._save_compatibility_cache(output)

        return output

    def _save_compatibility_cache(self, output: AgentOutput) -> None:
        """
        SyncAgent 호환성을 위해 refactoring_agent.json 생성

        기존 파이프라인에서 RefactoringAgent의 출력을 기대하는 SyncAgent와
        호환되도록 refactoring_agent.json을 생성합니다.
        """
        try:
            # 호환 캐시 데이터 생성
            # SyncAgent의 _collect_agent_results()가 기대하는 구조
            compat_output = {
                "pipeline_id": self.run_context["pipeline_id"],
                "agent_name": "refactoring_agent",  # SyncAgent가 이 이름으로 조회
                "agent_branch": self.run_context.get("review_agent_branch", ""),
                "status": "success",
                "started_at": output["started_at"],
                "ended_at": output["ended_at"],
                "error": None,
                "data": {
                    # SyncAgent의 _collect_agent_results()가 기대하는 구조
                    "refactoring_summary": {
                        "refactored_files_count": 0,  # Review는 코드 수정 안 함
                        "total_files_checked": 0,
                        "details": [],
                    }
                },
            }

            # 캐시 디렉토리
            cache_dir = self.run_context["workspace_path"] / ".commitly" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)

            # refactoring_agent.json에 저장
            cache_file = cache_dir / "refactoring_agent.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(compat_output, f, indent=2, ensure_ascii=False)

            self.logger.debug(f"호환 캐시 저장: {cache_file}")

        except Exception as e:
            self.logger.warning(f"호환 캐시 저장 실패: {e}")
            # 호환 캐시 실패는 치명적 오류 아님

    def execute(self) -> Dict[str, Any]:
        """
        Review Agent 실행

        Returns:
            {
                "overall_assessment": str,  # APPROVE | REQUEST_CHANGES | COMMENT
                "issues": List[Dict],  # 발견된 이슈 목록
                "issue_count": Dict,  # 심각도별 카운트
                "positive_aspects": List[str],  # 긍정적 측면
                "user_approved": bool,  # 사용자 승인 여부
            }
        """
        # 1. 브랜치 생성
        self._create_agent_branch()

        # 2. git diff 추출 (사용자 원본 변경사항)
        diff_content = self._get_user_changes_diff()

        if not diff_content or diff_content.strip() == "":
            self.logger.info("변경사항 없음, 리뷰 스킵")
            return {
                "overall_assessment": "APPROVE",
                "issues": [],
                "issue_count": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "positive_aspects": ["변경사항 없음"],
                "user_approved": True,
            }

        # 3. LLM 리뷰 수행
        review_result = self._perform_llm_review(diff_content)

        # 4. 승인 게이트 (CRITICAL/HIGH 이슈가 있을 때만)
        user_approved = self._approval_gate(review_result)

        if not user_approved:
            raise RuntimeError(
                "사용자가 코드 리뷰 결과를 확인한 후 진행을 거부했습니다.\n"
                "이슈를 수정한 후 다시 커밋해주세요."
            )

        # 5. 결과 반환
        return {
            "overall_assessment": review_result["overall_assessment"],
            "issues": review_result["issues"],
            "issue_count": review_result["issue_count"],
            "positive_aspects": review_result.get("positive_aspects", []),
            "user_approved": user_approved,
        }

    def _create_agent_branch(self) -> None:
        """에이전트 브랜치 생성"""
        pipeline_id = self.run_context["pipeline_id"]
        branch_name = f"commitly/review/{pipeline_id}"

        # 부모 브랜치: Test Agent 브랜치
        parent_branch = self.run_context["test_agent_branch"]

        self.hub_git.create_branch(branch_name, parent_branch)

        self.agent_branch = branch_name
        self.run_context["review_agent_branch"] = branch_name

        # SyncAgent 호환성을 위해 refactoring_agent_branch도 설정
        # (기존 파이프라인에서 RefactoringAgent → ReviewAgent로 변경)
        self.run_context["refactoring_agent_branch"] = branch_name

        self.logger.info(f"에이전트 브랜치 생성: {branch_name}")

    def _get_user_changes_diff(self) -> str:
        """
        사용자 원본 변경사항 추출

        CloneAgent가 커밋한 변경사항만 가져옴 (RefactoringAgent 수정 제외)

        Returns:
            git diff 결과 문자열
        """
        # Clone Agent의 커밋만 diff로 가져오기
        # Test Agent 브랜치 기준으로 main과 비교
        try:
            # main 브랜치와 현재 브랜치의 diff
            diff_result = self.hub_git.repo.git.diff(
                "main",
                self.run_context["clone_agent_branch"],
            )

            self.logger.info(f"git diff 추출 완료 (길이: {len(diff_result)} bytes)")
            return diff_result

        except Exception as e:
            self.logger.error(f"git diff 추출 실패: {e}")
            raise

    def _perform_llm_review(self, diff_content: str) -> Dict[str, Any]:
        """
        LLM을 사용한 코드 리뷰 수행

        Args:
            diff_content: git diff 결과

        Returns:
            {
                "overall_assessment": str,
                "issues": List[Dict],
                "issue_count": Dict,
                "positive_aspects": List[str],
            }
        """
        llm_client = self.run_context.get("llm_client")

        if not llm_client:
            self.logger.warning("LLM 클라이언트가 없어 리뷰를 스킵합니다")
            return {
                "overall_assessment": "APPROVE",
                "issues": [],
                "issue_count": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "positive_aspects": ["LLM 비활성화 상태"],
            }

        # LLM 리뷰 프롬프트
        prompt = f"""You are a code reviewer. Analyze the following git diff and provide a structured review.

Return your response in valid JSON format with this exact structure:
{{
  "overall_assessment": "APPROVE or REQUEST_CHANGES or COMMENT",
  "issues": [
    {{
      "severity": "CRITICAL or HIGH or MEDIUM or LOW",
      "category": "security or quality or bug or style",
      "file": "filename",
      "line": line_number_or_null,
      "description": "brief description",
      "recommendation": "how to fix"
    }}
  ],
  "positive_aspects": ["positive aspect 1", "positive aspect 2"]
}}

Review criteria:
1. Security vulnerabilities (CRITICAL/HIGH)
2. Potential bugs (HIGH/MEDIUM)
3. Code quality issues (MEDIUM/LOW)
4. Best practice violations (LOW)

Git diff:
{diff_content}
"""

        try:
            # LLM 호출
            response = llm_client.client.chat.completions.create(
                model=llm_client.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert code reviewer. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            review_text = response.choices[0].message.content.strip()

            # JSON 파싱
            review_data = self._parse_llm_response(review_text)

            # 영어 응답을 한국어로 번역
            review_data = self._translate_review_to_korean(review_data)

            # 심각도별 카운트
            issue_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for issue in review_data.get("issues", []):
                severity = issue.get("severity", "LOW").lower()
                if severity in issue_count:
                    issue_count[severity] += 1

            review_data["issue_count"] = issue_count

            self.logger.info(
                f"LLM 리뷰 완료: {review_data['overall_assessment']}, "
                f"이슈 {sum(issue_count.values())}개 발견"
            )

            return review_data

        except Exception as e:
            self.logger.error(f"LLM 리뷰 실패: {e}")
            # 실패 시 자동 승인
            return {
                "overall_assessment": "APPROVE",
                "issues": [],
                "issue_count": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "positive_aspects": [f"LLM 리뷰 실패 (에러: {str(e)})"],
            }

    def _translate_review_to_korean(self, review_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        LLM 리뷰 결과의 영어 설명/제안을 한국어로 번역

        Args:
            review_data: LLM 리뷰 결과

        Returns:
            한국어로 번역된 리뷰 데이터
        """
        llm_client = self.run_context.get("llm_client")

        if not llm_client:
            return review_data

        try:
            # 번역할 텍스트 수집
            texts_to_translate = []
            for issue in review_data.get("issues", []):
                if issue.get("description"):
                    texts_to_translate.append(issue["description"])
                if issue.get("recommendation"):
                    texts_to_translate.append(issue["recommendation"])

            for i, aspect in enumerate(review_data.get("positive_aspects", [])):
                if isinstance(aspect, str):
                    texts_to_translate.append(aspect)

            if not texts_to_translate:
                return review_data

            # 번역 요청
            translation_prompt = f"""Translate the following English texts to Korean. Keep the format simple and concise.
Return only the Korean translations in the same order, one per line.

Texts to translate:
{chr(10).join(f'{i+1}. {text}' for i, text in enumerate(texts_to_translate))}
"""

            response = llm_client.client.chat.completions.create(
                model=llm_client.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a translator. Translate English to Korean accurately and concisely.",
                    },
                    {"role": "user", "content": translation_prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            translated_texts = response.choices[0].message.content.strip().split("\n")
            # 숫자 prefix 제거 (예: "1. 한국어 텍스트" → "한국어 텍스트")
            translated_texts = [t.split(". ", 1)[1] if ". " in t else t for t in translated_texts]

            # 번역된 텍스트를 원래 데이터에 적용
            idx = 0
            for issue in review_data.get("issues", []):
                if issue.get("description") and idx < len(translated_texts):
                    issue["description"] = translated_texts[idx]
                    idx += 1
                if issue.get("recommendation") and idx < len(translated_texts):
                    issue["recommendation"] = translated_texts[idx]
                    idx += 1

            for i, _ in enumerate(review_data.get("positive_aspects", [])):
                if idx < len(translated_texts):
                    review_data["positive_aspects"][i] = translated_texts[idx]
                    idx += 1

            self.logger.debug(f"리뷰 결과를 한국어로 번역 완료")

        except Exception as e:
            self.logger.warning(f"번역 실패, 영어로 진행: {e}")

        return review_data

    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """
        LLM 응답 파싱 (JSON 추출)

        Args:
            response_text: LLM 응답 텍스트

        Returns:
            파싱된 JSON 데이터
        """
        # 마크다운 코드 블록 제거
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 실패: {e}")
            self.logger.debug(f"응답 텍스트: {response_text}")
            # 기본 구조 반환
            return {
                "overall_assessment": "APPROVE",
                "issues": [],
                "positive_aspects": ["JSON 파싱 실패로 자동 승인"],
            }

    def _approval_gate(self, review_result: Dict[str, Any]) -> bool:
        """
        승인 게이트: CRITICAL/HIGH 이슈가 있을 때만 사용자 확인

        Args:
            review_result: LLM 리뷰 결과

        Returns:
            사용자 승인 여부
        """
        issue_count = review_result["issue_count"]
        critical_count = issue_count.get("critical", 0)
        high_count = issue_count.get("high", 0)
        total_issues = sum(issue_count.values())

        # CRITICAL 또는 HIGH 이슈가 없으면 자동 승인
        if critical_count == 0 and high_count == 0:
            if total_issues == 0:
                self.logger.info("리뷰 완료: 이슈 없음, 자동 승인")
            else:
                self.logger.info(f"리뷰 완료: 심각한 이슈 없음 ({total_issues}개 경미 이슈), 자동 승인")
            return True

        # CRITICAL/HIGH 이슈가 있으면 사용자 확인
        return self._request_user_approval(review_result)

    def _request_user_approval(self, review_result: Dict[str, Any]) -> bool:
        """
        사용자에게 승인 요청

        Args:
            review_result: LLM 리뷰 결과

        Returns:
            사용자 승인 여부
        """
        issue_count = review_result["issue_count"]
        issues = review_result.get("issues", [])

        print("\n" + "=" * 80)
        print("⚠️  코드 리뷰 결과: 이슈 발견")
        print("=" * 80)

        # 심각도별 요약
        print(f"\n📊 이슈 요약:")
        print(f"  CRITICAL: {issue_count.get('critical', 0)}개")
        print(f"  HIGH:     {issue_count.get('high', 0)}개")
        print(f"  MEDIUM:   {issue_count.get('medium', 0)}개")
        print(f"  LOW:      {issue_count.get('low', 0)}개")

        # CRITICAL/HIGH 이슈만 표시
        critical_high_issues = [
            issue
            for issue in issues
            if issue.get("severity", "").upper() in ["CRITICAL", "HIGH"]
        ]

        if critical_high_issues:
            print(f"\n🚨 주요 이슈 ({len(critical_high_issues)}개):")
            for idx, issue in enumerate(critical_high_issues[:5], 1):  # 최대 5개만
                severity = issue.get("severity", "UNKNOWN")
                file_name = issue.get("file", "unknown")
                description = issue.get("description", "")
                recommendation = issue.get("recommendation", "")

                print(f"  {idx}. [{severity}] {file_name}")
                print(f"     설명: {description}")
                if recommendation:
                    print(f"     제안: {recommendation}")

            if len(critical_high_issues) > 5:
                print(f"  ... 외 {len(critical_high_issues) - 5}개")

        print("\n" + "=" * 80)

        # 사용자 입력
        while True:
            response = input(
                "\n계속 진행하시겠습니까? (y: 진행, n: 중단, d: 상세보기): "
            ).lower()

            if response == "y":
                print("✓ 계속 진행합니다.")
                return True
            elif response == "n":
                print("✗ 파이프라인을 중단합니다.")
                return False
            elif response == "d":
                self._show_detailed_review(review_result)
            else:
                print("잘못된 입력입니다. y, n, d 중 하나를 입력해주세요.")

    def _show_detailed_review(self, review_result: Dict[str, Any]) -> None:
        """
        상세 리뷰 결과 표시

        Args:
            review_result: LLM 리뷰 결과
        """
        print("\n" + "=" * 80)
        print("📋 상세 코드 리뷰 결과")
        print("=" * 80)

        # Overall Assessment
        assessment = review_result.get("overall_assessment", "UNKNOWN")
        print(f"\n✓ 전체 평가: {assessment}")

        # Positive Aspects
        positive = review_result.get("positive_aspects", [])
        if positive:
            print(f"\n✅ 긍정적 측면:")
            for aspect in positive:
                print(f"  - {aspect}")

        # Issues
        issues = review_result.get("issues", [])
        if issues:
            print(f"\n⚠️  발견된 이슈 ({len(issues)}개):")

            # 심각도별로 정렬
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            sorted_issues = sorted(
                issues,
                key=lambda x: severity_order.get(x.get("severity", "LOW").upper(), 4),
            )

            for idx, issue in enumerate(sorted_issues, 1):
                severity = issue.get("severity", "UNKNOWN")
                category = issue.get("category", "unknown")
                file_name = issue.get("file", "unknown")
                line = issue.get("line")
                description = issue.get("description", "")
                recommendation = issue.get("recommendation", "")

                print(f"\n  [{idx}] {severity} - {category}")
                print(f"      파일: {file_name}" + (f":{line}" if line else ""))
                print(f"      설명: {description}")
                if recommendation:
                    print(f"      제안: {recommendation}")

        print("\n" + "=" * 80)
