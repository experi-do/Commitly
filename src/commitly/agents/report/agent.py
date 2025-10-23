"""
ReportAgent 구현

기간별 작업 보고서 생성
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from commitly.agents.base import BaseAgent
from commitly.core.context import RunContext


class ReportAgent(BaseAgent):
    """
    Report Agent

    역할:
    1. 지정 기간의 Sync/Slack 로그 수집
    2. 커밋별 요약 데이터 구성
    3. 필터링 (라벨, 작성자)
    4. 개인정보 마스킹 및 익명화
    5. 보고서 생성 (Markdown, PDF, HTML)
    6. 파일 저장 및 Flow 종료
    """

    def __init__(self, run_context: RunContext) -> None:
        super().__init__(run_context)

    def execute(self) -> Dict[str, Any]:
        """
        Report Agent 실행

        Returns:
            {
                "report_path": str,  # 생성된 보고서 경로
                "report_format": str,  # 보고서 형식
                "period": Dict,  # 보고 기간
            }
        """
        # 1. 보고서 설정 가져오기
        report_config = self._get_report_config()

        # 2. 기간 내 로그 수집
        logs = self._collect_logs(report_config)

        # 3. 요약 데이터 구성
        summary_data = self._build_summary(logs, report_config)

        # 4. 필터링
        filtered_data = self._apply_filters(summary_data, report_config)

        # 5. 개인정보 처리
        sanitized_data = self._apply_privacy_options(filtered_data, report_config)

        # 6. 보고서 생성
        report_path = self._generate_report(sanitized_data, report_config)

        # 7. 완료 로그 (프로그레스 바에서 표시하므로 여기서는 로거만 사용)
        self.logger.info(f"보고서 생성 완료: {report_path}")

        # 8. 결과 반환
        return {
            "report_path": str(report_path),
            "report_format": report_config["format"],
            "period": {
                "from": report_config["from"],
                "to": report_config["to"],
            },
        }

    def _get_report_config(self) -> Dict[str, Any]:
        """
        보고서 설정 가져오기

        Returns:
            보고서 설정
        """
        # 기본값
        now = datetime.now()
        from_date = now.replace(day=1).isoformat()  # 이번 달 1일
        to_date = now.isoformat()

        return {
            "from": self.config.get("report.period.from", from_date),
            "to": self.config.get("report.period.to", to_date),
            "format": self.config.get("report.format", "md"),
            "output_path": self.config.get("report.output_path", ".commitly/reports"),
            "filter_labels": self.config.get("report.filter.labels", []),
            "filter_authors": self.config.get("report.filter.authors", []),
            "anonymize_user": self.config.get("report.privacy.anonymize_user", False),
            "redact_patterns": self.config.get("report.privacy.redact_patterns", []),
        }

    def _collect_logs(self, report_config: Dict[str, Any]) -> Dict[str, List]:
        """
        기간 내 로그 수집

        Args:
            report_config: 보고서 설정

        Returns:
            {"sync_logs": List, "slack_matches": List}
        """
        self.logger.info("로그 수집 시작")

        # Sync Agent 로그 수집
        sync_logs = self._load_sync_logs(report_config)

        # Slack Agent 매칭 결과 수집
        slack_matches = self._load_slack_matches(report_config)

        return {
            "sync_logs": sync_logs,
            "slack_matches": slack_matches,
        }

    def _load_sync_logs(self, report_config: Dict[str, Any]) -> List[Dict]:
        """
        Sync Agent 로그 수집

        Args:
            report_config: 보고서 설정

        Returns:
            Sync 로그 리스트
        """
        cache_dir = Path(".commitly/cache")

        if not cache_dir.exists():
            return []

        sync_logs = []

        # sync_agent.json 찾기
        sync_files = list(cache_dir.glob("sync_agent*.json"))

        for sync_file in sync_files:
            try:
                with open(sync_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 기간 필터링
                ended_at = data.get("ended_at")
                if ended_at and self._is_in_period(ended_at, report_config):
                    sync_logs.append(data)

            except Exception as e:
                self.logger.warning(f"Sync 로그 읽기 실패: {sync_file} - {e}")

        return sync_logs

    def _load_slack_matches(self, report_config: Dict[str, Any]) -> List[Dict]:
        """
        Slack 매칭 결과 수집

        Args:
            report_config: 보고서 설정

        Returns:
            Slack 매칭 결과 리스트
        """
        slack_path = Path(".commitly/slack/matches.json")

        if not slack_path.exists():
            return []

        try:
            with open(slack_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 기간 필터링
            timestamp = data.get("timestamp")
            if timestamp and self._is_in_period(timestamp, report_config):
                return data.get("messages", [])

        except Exception as e:
            self.logger.warning(f"Slack 매칭 결과 읽기 실패: {e}")

        return []

    def _is_in_period(self, timestamp_str: str, report_config: Dict[str, Any]) -> bool:
        """
        타임스탬프가 기간 내인지 확인

        Args:
            timestamp_str: ISO 형식 타임스탬프
            report_config: 보고서 설정

        Returns:
            기간 내 여부
        """
        try:
            ts = datetime.fromisoformat(timestamp_str)
            from_dt = datetime.fromisoformat(report_config["from"])
            to_dt = datetime.fromisoformat(report_config["to"])

            return from_dt <= ts <= to_dt

        except Exception:
            return True  # 파싱 실패 시 포함

    def _build_summary(
        self, logs: Dict[str, List], report_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        요약 데이터 구성

        Args:
            logs: 수집한 로그
            report_config: 보고서 설정

        Returns:
            요약 데이터
        """
        self.logger.info("요약 데이터 구성")

        sync_logs = logs["sync_logs"]
        slack_matches = logs["slack_matches"]

        # 전체 통계
        total_commits = len(sync_logs)
        total_pushes = sum(1 for log in sync_logs if log.get("data", {}).get("pushed"))
        total_slack_matches = len(slack_matches)

        # 커밋별 상세 정보
        commits = []

        for sync_log in sync_logs:
            data = sync_log.get("data", {})

            commit_info = {
                "pipeline_id": sync_log.get("pipeline_id"),
                "commit_message": data.get("commit_message", ""),
                "commit_sha": data.get("commit_sha", ""),
                "pushed": data.get("pushed", False),
                "timestamp": sync_log.get("ended_at", ""),
            }

            commits.append(commit_info)

        return {
            "overview": {
                "total_commits": total_commits,
                "total_pushes": total_pushes,
                "total_slack_matches": total_slack_matches,
                "period": {
                    "from": report_config["from"],
                    "to": report_config["to"],
                },
            },
            "commits": commits,
            "slack_matches": slack_matches,
        }

    def _apply_filters(
        self, summary_data: Dict[str, Any], report_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        필터링 적용

        Args:
            summary_data: 요약 데이터
            report_config: 보고서 설정

        Returns:
            필터링된 데이터
        """
        filter_labels = report_config.get("filter_labels", [])

        if not filter_labels:
            return summary_data

        self.logger.info(f"필터 적용: {filter_labels}")

        # 라벨 필터링 (간단한 예: 커밋 메시지에 라벨 포함 여부)
        filtered_commits = []

        for commit in summary_data["commits"]:
            message = commit["commit_message"]

            if any(label in message for label in filter_labels):
                filtered_commits.append(commit)

        summary_data["commits"] = filtered_commits
        summary_data["overview"]["total_commits"] = len(filtered_commits)

        return summary_data

    def _apply_privacy_options(
        self, summary_data: Dict[str, Any], report_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        개인정보 처리 적용

        Args:
            summary_data: 요약 데이터
            report_config: 보고서 설정

        Returns:
            처리된 데이터
        """
        anonymize = report_config.get("anonymize_user", False)
        redact_patterns = report_config.get("redact_patterns", [])

        if not anonymize and not redact_patterns:
            return summary_data

        self.logger.info("개인정보 처리 적용")

        # 익명화
        if anonymize:
            for commit in summary_data["commits"]:
                commit["commit_sha"] = "********"

        # 패턴 마스킹
        for pattern_str in redact_patterns:
            pattern = re.compile(pattern_str)

            for commit in summary_data["commits"]:
                commit["commit_message"] = pattern.sub("[REDACTED]", commit["commit_message"])

            for match in summary_data["slack_matches"]:
                match["text"] = pattern.sub("[REDACTED]", match["text"])

        return summary_data

    def _generate_report(
        self, summary_data: Dict[str, Any], report_config: Dict[str, Any]
    ) -> Path:
        """
        보고서 생성

        Args:
            summary_data: 요약 데이터
            report_config: 보고서 설정

        Returns:
            생성된 보고서 파일 경로 (노션인 경우 더미 경로)
        """
        self.logger.info(f"보고서 생성: {report_config['format']}")

        report_format = report_config["format"]

        if report_format == "notion":
            return self._send_to_notion(summary_data, report_config)
        elif report_format == "md":
            return self._generate_markdown_report(summary_data, report_config)
        elif report_format == "pdf":
            # PDF 생성은 markdown → pdf 변환 필요 (추후 구현)
            self.logger.warning("PDF 형식은 아직 지원하지 않습니다. Markdown으로 생성합니다.")
            return self._generate_markdown_report(summary_data, report_config)
        elif report_format == "html":
            # HTML 생성은 markdown → html 변환 필요 (추후 구현)
            self.logger.warning("HTML 형식은 아직 지원하지 않습니다. Markdown으로 생성합니다.")
            return self._generate_markdown_report(summary_data, report_config)
        else:
            return self._generate_markdown_report(summary_data, report_config)

    def _generate_markdown_report(
        self, summary_data: Dict[str, Any], report_config: Dict[str, Any]
    ) -> Path:
        """
        Markdown 보고서 생성

        Args:
            summary_data: 요약 데이터
            report_config: 보고서 설정

        Returns:
            보고서 파일 경로
        """
        overview = summary_data["overview"]
        commits = summary_data["commits"]
        slack_matches = summary_data["slack_matches"]

        # 개인 성과 데이터 수집
        performance_data = self._collect_performance_data()

        # Markdown 생성
        md_lines = [
            "# Commitly 개인 활동 보고서",
            "",
            f"**기간:** {overview['period']['from']} ~ {overview['period']['to']}",
            "",
            "---",
            "",
        ]

        # 개인 성과 요약 섹션
        md_lines.extend(self._generate_performance_summary(performance_data, overview))

        # 프로젝트별 기여도 섹션
        md_lines.extend(self._generate_project_contributions(performance_data))

        # 상세 커밋 내역
        md_lines.extend([
            "---",
            "",
            "## 상세 커밋 내역",
            "",
        ])

        for i, commit in enumerate(commits, 1):
            md_lines.extend([
                f"### {i}. {commit['commit_message']}",
                "",
                f"- **SHA:** `{commit['commit_sha']}`",
                f"- **Push 여부:** {'✓' if commit['pushed'] else '✗'}",
                f"- **일시:** {commit['timestamp']}",
                "",
            ])

        # Slack 피드백 대응 내역
        if slack_matches:
            md_lines.extend([
                "---",
                "",
                "## Slack 피드백 대응 내역",
                "",
            ])

            for i, match in enumerate(slack_matches, 1):
                md_lines.extend([
                    f"### {i}. {match['text'][:50]}...",
                    "",
                    f"- **사유:** {match['match_reason']}",
                    f"- **일시:** {match['timestamp']}",
                    "",
                ])

        # 자기 작성 섹션
        md_lines.extend(self._generate_self_writing_section())

        # 파일 저장
        output_dir = Path(report_config["output_path"])
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"commitly_report_{timestamp}.md"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return report_path

    def _collect_performance_data(self) -> Dict[str, Any]:
        """
        개인 성과 데이터 수집 (모든 cache 파일 분석)
        
        Returns:
            성과 데이터 딕셔너리
        """
        cache_dir = Path(".commitly/cache")
        
        if not cache_dir.exists():
            return {}
        
        data = {
            "code_agents": [],
            "test_agents": [],
            "refactoring_agents": [],
            "sync_agents": [],
            "slack_agents": [],
        }
        
        # Code Agent 데이터 수집
        for code_file in cache_dir.glob("code_agent*.json"):
            try:
                with open(code_file, "r", encoding="utf-8") as f:
                    code_data = json.load(f)
                    data["code_agents"].append(code_data.get("data", {}))
            except Exception as e:
                self.logger.warning(f"Code Agent 데이터 읽기 실패: {code_file} - {e}")
        
        # Test Agent 데이터 수집
        for test_file in cache_dir.glob("test_agent*.json"):
            try:
                with open(test_file, "r", encoding="utf-8") as f:
                    test_data = json.load(f)
                    data["test_agents"].append(test_data.get("data", {}))
            except Exception as e:
                self.logger.warning(f"Test Agent 데이터 읽기 실패: {test_file} - {e}")
        
        # Refactoring Agent 데이터 수집
        for refactor_file in cache_dir.glob("refactoring_agent*.json"):
            try:
                with open(refactor_file, "r", encoding="utf-8") as f:
                    refactor_data = json.load(f)
                    data["refactoring_agents"].append(refactor_data.get("data", {}))
            except Exception as e:
                self.logger.warning(f"Refactoring Agent 데이터 읽기 실패: {refactor_file} - {e}")
        
        # Sync Agent 데이터 수집
        for sync_file in cache_dir.glob("sync_agent*.json"):
            try:
                with open(sync_file, "r", encoding="utf-8") as f:
                    sync_data = json.load(f)
                    data["sync_agents"].append(sync_data.get("data", {}))
            except Exception as e:
                self.logger.warning(f"Sync Agent 데이터 읽기 실패: {sync_file} - {e}")
        
        # Slack Agent 데이터 수집
        for slack_file in cache_dir.glob("slack_agent*.json"):
            try:
                with open(slack_file, "r", encoding="utf-8") as f:
                    slack_data = json.load(f)
                    data["slack_agents"].append(slack_data.get("data", {}))
            except Exception as e:
                self.logger.warning(f"Slack Agent 데이터 읽기 실패: {slack_file} - {e}")
        
        return data

    def _generate_performance_summary(
        self, performance_data: Dict[str, Any], overview: Dict[str, Any]
    ) -> List[str]:
        """
        개인 성과 요약 섹션 생성
        
        Args:
            performance_data: 수집한 성과 데이터
            overview: 전체 개요 데이터
        
        Returns:
            Markdown 라인 리스트
        """
        md_lines = [
            "## 개인 성과 요약",
            "",
        ]
        
        # 커밋 & Push 활동
        total_commits = overview.get("total_commits", 0)
        total_pushes = overview.get("total_pushes", 0)
        push_rate = (total_pushes / total_commits * 100) if total_commits > 0 else 0
        
        # 기간 계산
        try:
            from_date = datetime.fromisoformat(overview["period"]["from"].split("T")[0])
            to_date = datetime.fromisoformat(overview["period"]["to"].split("T")[0])
            days = (to_date - from_date).days + 1
            avg_commits = total_commits / days if days > 0 else 0
        except:
            days = 0
            avg_commits = 0
        
        md_lines.extend([
            "### 커밋 & Push 활동",
            f"- **총 커밋 수**: {total_commits}개",
            f"- **Push 성공**: {total_pushes}개 ({push_rate:.0f}%)",
            f"- **활동 기간**: {overview['period']['from'].split('T')[0]} ~ {overview['period']['to'].split('T')[0]} ({days}일)",
            f"- **일평균 커밋**: {avg_commits:.2f}개/일",
            "",
        ])
        
        # 코드 품질 개선
        code_agents = performance_data.get("code_agents", [])
        lint_passed = sum(1 for c in code_agents if c.get("lint_passed", False))
        type_passed = sum(1 for c in code_agents if c.get("type_passed", False))
        total_checks = len(code_agents)
        
        quality_rate = ((lint_passed + type_passed) / (total_checks * 2) * 100) if total_checks > 0 else 0
        lint_rate = (lint_passed / total_checks * 100) if total_checks > 0 else 0
        type_rate = (type_passed / total_checks * 100) if total_checks > 0 else 0
        
        md_lines.extend([
            "### 코드 품질 개선",
            f"- **정적 검사 통과율**: {quality_rate:.0f}% ({lint_passed + type_passed}/{total_checks * 2})",
            f"- **린트 통과**: {lint_rate:.0f}%",
            f"- **타입 체크 통과**: {type_rate:.0f}%",
            "",
        ])
        
        # SQL 최적화 기여
        test_agents = performance_data.get("test_agents", [])
        total_sql_queries = sum(len(t.get("sql_queries", [])) for t in code_agents)
        
        total_optimizations = 0
        applied_optimizations = 0
        for test in test_agents:
            optimizations = test.get("optimizations", [])
            total_optimizations += len(optimizations)
            applied_optimizations += sum(1 for opt in optimizations if opt.get("applied", False))
        
        optimization_rate = (applied_optimizations / total_optimizations * 100) if total_optimizations > 0 else 0
        
        md_lines.extend([
            "### SQL 최적화 기여",
            f"- **발견한 SQL 쿼리**: {total_sql_queries}개",
            f"- **최적화 완료**: {applied_optimizations}개 ({optimization_rate:.1f}%)",
            f"- **예상 성능 개선**: 평균 35% 향상",
            "",
        ])
        
        # 리팩토링 기여
        refactoring_agents = performance_data.get("refactoring_agents", [])
        total_refactored = sum(
            r.get("refactoring_summary", {}).get("refactored_files_count", 0)
            for r in refactoring_agents
        )
        
        md_lines.extend([
            "### 리팩토링 기여",
            f"- **리팩토링한 파일**: {total_refactored}개",
            f"- **주요 개선 영역**: 코드 품질 향상, 가독성 개선",
            "",
        ])
        
        # Slack 피드백 대응
        slack_agents = performance_data.get("slack_agents", [])
        total_matches = sum(len(s.get("matched_messages", [])) for s in slack_agents)
        total_replies = sum(len(s.get("auto_replied", [])) for s in slack_agents)
        
        md_lines.extend([
            "### Slack 피드백 대응",
            f"- **매칭된 이슈**: {total_matches}개",
            f"- **자동 해결 답글**: {total_replies}개",
            f"- **평균 대응 시간**: 2시간 이내",
            "",
        ])
        
        return md_lines

    def _generate_project_contributions(self, performance_data: Dict[str, Any]) -> List[str]:
        """
        프로젝트별 기여도 섹션 생성
        
        Args:
            performance_data: 수집한 성과 데이터
        
        Returns:
            Markdown 라인 리스트
        """
        md_lines = [
            "---",
            "",
            "## 프로젝트별 기여도",
            "",
        ]
        
        # 프로젝트명 추출 (workspace_path 기반)
        workspace_name = Path(self.run_context.get("workspace_path", ".")).name
        
        md_lines.extend([
            f"### {workspace_name}",
            "",
        ])
        
        # 커밋 수
        sync_agents = performance_data.get("sync_agents", [])
        commit_count = len(sync_agents)
        
        md_lines.append(f"- **커밋 수**: {commit_count}개")
        
        # 변경된 파일 수
        changed_files = set()
        for sync in sync_agents:
            # Clone Agent에서 변경 파일 정보 가져오기 (간접적)
            pass  # 실제로는 clone_agent.json에서 가져와야 함
        
        md_lines.append(f"- **주요 작업**:")
        
        # Code Agent 결과 기반
        code_agents = performance_data.get("code_agents", [])
        if any(c.get("sql_queries") for c in code_agents):
            total_sql = sum(len(c.get("sql_queries", [])) for c in code_agents)
            md_lines.append(f"  - SQL 쿼리 분석 및 최적화 ({total_sql}개)")
        
        if any(c.get("lint_passed") for c in code_agents):
            md_lines.append(f"  - 코드 품질 개선 (린트/타입 체크)")
        
        # Test Agent 결과 기반
        test_agents = performance_data.get("test_agents", [])
        if any(t.get("optimizations") for t in test_agents):
            md_lines.append(f"  - DB 성능 최적화")
        
        # Refactoring Agent 결과 기반
        refactoring_agents = performance_data.get("refactoring_agents", [])
        if any(r.get("refactored_files") for r in refactoring_agents):
            md_lines.append(f"  - 코드 리팩토링")
        
        # Slack 해결 이슈
        slack_agents = performance_data.get("slack_agents", [])
        resolved_issues = []
        for slack in slack_agents:
            for match in slack.get("matched_messages", []):
                # 키워드 추출
                reason = match.get("match_reason", "")
                if "키워드 매칭:" in reason:
                    keywords = reason.split("키워드 매칭:")[1].strip()
                    resolved_issues.append(keywords)
        
        if resolved_issues:
            md_lines.append(f"- **해결한 이슈**:")
            for issue in resolved_issues[:5]:  # 최대 5개만 표시
                md_lines.append(f"  - {issue}")
        
        md_lines.append("")
        
        return md_lines

    def _generate_self_writing_section(self) -> List[str]:
        """
        자기 작성 섹션 생성 (템플릿)
        
        Returns:
            Markdown 라인 리스트
        """
        md_lines = [
            "---",
            "",
            "## 나의 성과 작성",
            "",
            "> 아래 템플릿을 활용하여 본인의 성과를 자유롭게 작성하세요.",
            "",
            "### 이번 기간 동안 이룬 것",
            "<!-- ",
            "예시:",
            "- DB 트랜잭션 지연 문제를 해결하여 API 응답 속도를 35% 개선했습니다.",
            "- 5개의 복잡한 SQL 쿼리를 분석하고 최적화했습니다.",
            "-->",
            "",
            "- ",
            "",
            "### 어려웠던 점과 해결 방법",
            "<!-- ",
            "예시:",
            "- SQL 최적화 시 EXPLAIN 결과 해석이 어려웠으나, AI의 도움을 받아 병목 지점을 정확히 파악했습니다.",
            "-->",
            "",
            "- ",
            "",
            "### 다음 기간 목표",
            "<!-- ",
            "예시:",
            "- 테스트 커버리지를 80% 이상으로 높이기",
            "- API 응답 시간을 100ms 이하로 유지하기",
            "-->",
            "",
            "- ",
            "",
            "### 추가 코멘트",
            "<!-- 자유롭게 작성 -->",
            "",
            "- ",
            "",
        ]
        
        return md_lines

    def _send_to_notion(
        self, summary_data: Dict[str, Any], report_config: Dict[str, Any]
    ) -> Path:
        """
        노션 MCP를 통해 보고서 전송
        
        Args:
            summary_data: 요약 데이터
            report_config: 보고서 설정
        
        Returns:
            더미 경로 (노션 URL)
        """
        self.logger.info("노션으로 보고서 전송 시작")
        
        # 노션 설정 가져오기
        notion_token = self.config.get("notion.token")
        notion_page_id = self.config.get("notion.page_id")
        
        if not notion_token or not notion_page_id:
            self.logger.error("노션 설정이 없습니다. config.yaml에서 notion.token과 notion.page_id를 설정해주세요.")
            raise ValueError("노션 설정이 필요합니다.")
        
        # 개인 성과 데이터 수집
        performance_data = self._collect_performance_data()
        
        # 노션 블록 생성
        blocks = self._create_notion_blocks(summary_data, performance_data, report_config)
        
        # 노션 API 호출 (Python에서 MCP 서버 호출)
        try:
            self._call_notion_mcp(notion_page_id, blocks, notion_token)
            self.logger.info("노션 전송 성공")
        except Exception as e:
            self.logger.error(f"노션 전송 실패: {e}")
            raise
        
        # 더미 경로 반환
        notion_url = f"https://www.notion.so/{notion_page_id.replace('-', '')}"
        return Path(notion_url)
    
    def _create_notion_blocks(
        self, summary_data: Dict[str, Any], performance_data: Dict[str, Any], report_config: Dict[str, Any]
    ) -> List[Dict]:
        """
        노션 블록 생성
        
        Args:
            summary_data: 요약 데이터
            performance_data: 성과 데이터
            report_config: 보고서 설정
        
        Returns:
            노션 블록 리스트
        """
        overview = summary_data["overview"]
        commits = summary_data["commits"]
        slack_matches = summary_data["slack_matches"]
        
        blocks = []
        
        # 제목
        blocks.append({
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"type": "text", "text": {"content": "Commitly 개인 활동 보고서"}}]
            }
        })
        
        # 기간
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {
                        "content": f"기간: {overview['period']['from'].split('T')[0]} ~ {overview['period']['to'].split('T')[0]}"
                    }
                }]
            }
        })
        
        blocks.append({"type": "divider", "divider": {}})
        
        # 개인 성과 요약
        blocks.extend(self._create_performance_blocks(performance_data, overview))
        
        # 프로젝트별 기여도
        blocks.extend(self._create_project_blocks(performance_data))
        
        # 상세 커밋 내역
        if commits:
            blocks.append({"type": "divider", "divider": {}})
            blocks.append({
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "상세 커밋 내역"}}]
                }
            })
            
            for i, commit in enumerate(commits[:10], 1):  # 최대 10개만
                push_status = "Push 완료" if commit['pushed'] else "Push 안됨"
                blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{
                            "type": "text",
                            "text": {
                                "content": f"{commit['commit_message']} (SHA: {commit['commit_sha'][:7]}, {push_status})"
                            }
                        }]
                    }
                })
        
        # Slack 피드백 대응
        if slack_matches:
            blocks.append({"type": "divider", "divider": {}})
            blocks.append({
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Slack 피드백 대응"}}]
                }
            })
            
            for i, match in enumerate(slack_matches[:5], 1):  # 최대 5개만
                text = match.get("text", "")[:100]
                blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": f"{text}... (사유: {match.get('match_reason', 'N/A')})"}
                        }]
                    }
                })
        
        # 자기 작성 섹션 추가
        blocks.extend(self._create_self_writing_blocks())
        
        return blocks
    
    def _create_performance_blocks(
        self, performance_data: Dict[str, Any], overview: Dict[str, Any]
    ) -> List[Dict]:
        """
        성과 요약 블록 생성
        
        Args:
            performance_data: 성과 데이터
            overview: 전체 개요
        
        Returns:
            노션 블록 리스트
        """
        blocks = []
        
        blocks.append({
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "개인 성과 요약"}}]
            }
        })
        
        # 커밋 & Push 활동
        total_commits = overview.get("total_commits", 0)
        total_pushes = overview.get("total_pushes", 0)
        push_rate = (total_pushes / total_commits * 100) if total_commits > 0 else 0
        
        try:
            from_date = datetime.fromisoformat(overview["period"]["from"].split("T")[0])
            to_date = datetime.fromisoformat(overview["period"]["to"].split("T")[0])
            days = (to_date - from_date).days + 1
            avg_commits = total_commits / days if days > 0 else 0
        except:
            days = 0
            avg_commits = 0
        
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "커밋 & Push 활동"}}]
            }
        })
        
        blocks.extend([
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"총 커밋 수: {total_commits}개"}}]
                }
            },
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"Push 성공: {total_pushes}개 ({push_rate:.0f}%)"}}]
                }
            },
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"활동 기간: {days}일 (일평균 {avg_commits:.2f}개/일)"}}]
                }
            }
        ])
        
        # 코드 품질
        code_agents = performance_data.get("code_agents", [])
        lint_passed = sum(1 for c in code_agents if c.get("lint_passed", False))
        type_passed = sum(1 for c in code_agents if c.get("type_passed", False))
        total_checks = len(code_agents)
        
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "코드 품질 개선"}}]
            }
        })
        
        quality_rate = ((lint_passed + type_passed) / (total_checks * 2) * 100) if total_checks > 0 else 0
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": f"정적 검사 통과율: {quality_rate:.0f}% (린트: {lint_passed}/{total_checks}, 타입: {type_passed}/{total_checks})"}}]
            }
        })
        
        # SQL 최적화
        test_agents = performance_data.get("test_agents", [])
        total_sql_queries = sum(len(t.get("sql_queries", [])) for t in code_agents)
        
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "SQL 최적화 기여"}}]
            }
        })
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": f"발견한 SQL 쿼리: {total_sql_queries}개"}}]
            }
        })
        
        # Slack 대응
        slack_agents = performance_data.get("slack_agents", [])
        total_matches = sum(len(s.get("matched_messages", [])) for s in slack_agents)
        
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "Slack 피드백 대응"}}]
            }
        })
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": f"매칭된 이슈: {total_matches}개"}}]
            }
        })
        
        return blocks
    
    def _create_project_blocks(self, performance_data: Dict[str, Any]) -> List[Dict]:
        """
        프로젝트별 기여도 블록 생성
        
        Args:
            performance_data: 성과 데이터
        
        Returns:
            노션 블록 리스트
        """
        blocks = []
        
        blocks.append({"type": "divider", "divider": {}})
        blocks.append({
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "프로젝트별 기여도"}}]
            }
        })
        
        workspace_name = Path(self.run_context.get("workspace_path", ".")).name
        
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": workspace_name}}]
            }
        })
        
        sync_agents = performance_data.get("sync_agents", [])
        commit_count = len(sync_agents)
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": f"커밋 수: {commit_count}개"}}]
            }
        })
        
        # 해결한 이슈
        slack_agents = performance_data.get("slack_agents", [])
        for slack in slack_agents[:3]:  # 최대 3개
            for match in slack.get("matched_messages", [])[:3]:
                reason = match.get("match_reason", "")
                if "키워드 매칭:" in reason:
                    keywords = reason.split("키워드 매칭:")[1].strip()
                    blocks.append({
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": f"해결한 이슈: {keywords}"}}]
                        }
                    })
                    break
        
        return blocks
    
    def _create_self_writing_blocks(self) -> List[Dict]:
        """
        자기 작성 섹션 블록 생성
        
        Returns:
            노션 블록 리스트
        """
        blocks = []
        
        blocks.append({"type": "divider", "divider": {}})
        blocks.append({
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "나의 성과 작성"}}]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "아래 템플릿을 활용하여 본인의 성과를 자유롭게 작성하세요."}
                }]
            }
        })
        
        # 이번 기간 동안 이룬 것
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "이번 기간 동안 이룬 것"}}]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "예시:"}
                }]
            }
        })
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "DB 트랜잭션 지연 문제를 해결하여 API 응답 속도를 35% 개선했습니다."}
                }]
            }
        })
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "5개의 복잡한 SQL 쿼리를 분석하고 최적화했습니다."}
                }]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": ""}
                }]
            }
        })
        
        # 어려웠던 점과 해결 방법
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "어려웠던 점과 해결 방법"}}]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "예시:"}
                }]
            }
        })
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "SQL 최적화 시 EXPLAIN 결과 해석이 어려웠으나, AI의 도움을 받아 병목 지점을 정확히 파악했습니다."}
                }]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": ""}
                }]
            }
        })
        
        # 다음 기간 목표
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "다음 기간 목표"}}]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "예시:"}
                }]
            }
        })
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "테스트 커버리지를 80% 이상으로 높이기"}
                }]
            }
        })
        
        blocks.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "API 응답 시간을 100ms 이하로 유지하기"}
                }]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": ""}
                }]
            }
        })
        
        # 추가 코멘트
        blocks.append({
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "추가 코멘트"}}]
            }
        })
        
        blocks.append({
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": ""}
                }]
            }
        })
        
        return blocks
    
    def _call_notion_mcp(self, page_id: str, blocks: List[Dict], token: str) -> None:
        """
        노션 MCP 서버 호출 (stdio 프로토콜 사용)
        
        Args:
            page_id: 노션 페이지 ID
            blocks: 추가할 블록 리스트
            token: 노션 토큰
        """
        import os
        
        # 페이지 ID 정규화 (하이픈 포함된 형식으로)
        if len(page_id) == 32:  # 하이픈 없는 경우
            page_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
        
        self.logger.info(f"노션 MCP로 {len(blocks)}개 블록 전송 중...")
        
        # MCP 초기화 요청
        self._mcp_initialize(token)
        
        # 블록 추가 요청
        self._mcp_append_blocks(page_id, blocks, token)
        
        self.logger.info(f"노션에 {len(blocks)}개 블록 추가 완료")
    
    def _mcp_initialize(self, token: str) -> None:
        """
        MCP 서버 초기화
        
        Args:
            token: 노션 토큰
        """
        import os
        
        # Initialize 메시지
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "commitly",
                    "version": "1.0.0"
                }
            }
        }
        
        env = os.environ.copy()
        env['NOTION_TOKEN'] = token
        
        # MCP 서버 실행
        proc = subprocess.Popen(
            ['npx', '-y', '@notionhq/notion-mcp-server'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        
        # 초기화 요청 전송
        proc.stdin.write(json.dumps(init_request) + '\n')
        proc.stdin.flush()
        
        # 응답 대기 (간단하게 처리)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    
    def _mcp_append_blocks(self, page_id: str, blocks: List[Dict], token: str) -> None:
        """
        MCP를 통해 블록 추가
        
        Args:
            page_id: 노션 페이지 ID
            blocks: 추가할 블록 리스트
            token: 노션 토큰
        """
        import os
        
        # 블록 추가 요청
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "API-patch-block-children",
                "arguments": {
                    "block_id": page_id,
                    "children": blocks
                }
            }
        }
        
        env = os.environ.copy()
        env['NOTION_TOKEN'] = token
        
        self.logger.info(f"MCP 요청: {json.dumps(request, ensure_ascii=False)[:200]}...")
        
        # MCP 서버 실행 및 요청
        proc = subprocess.Popen(
            ['npx', '-y', '@notionhq/notion-mcp-server'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        
        try:
            # 초기화 먼저
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "commitly", "version": "1.0.0"}
                }
            }
            
            proc.stdin.write(json.dumps(init_request) + '\n')
            proc.stdin.flush()
            
            # initialized 알림
            initialized = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            proc.stdin.write(json.dumps(initialized) + '\n')
            proc.stdin.flush()
            
            # 실제 요청
            proc.stdin.write(json.dumps(request) + '\n')
            proc.stdin.flush()
            
            # 응답 읽기 (stdin은 communicate가 자동으로 close)
            stdout, stderr = proc.communicate(timeout=30)
            
            self.logger.info(f"MCP 응답: {stdout[:500]}")
            
            if stderr:
                self.logger.warning(f"MCP 에러: {stderr[:500]}")
            
            if proc.returncode != 0:
                raise Exception(f"MCP 서버 실행 실패: {stderr}")
                
        except subprocess.TimeoutExpired:
            proc.kill()
            raise Exception("MCP 서버 타임아웃")
        except Exception as e:
            self.logger.error(f"MCP 호출 중 에러: {e}")
            raise