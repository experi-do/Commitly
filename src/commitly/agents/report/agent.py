"""
ReportAgent 구현

기간별 작업 보고서 생성
"""

import json
import re
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
            생성된 보고서 파일 경로
        """
        self.logger.info(f"보고서 생성: {report_config['format']}")

        report_format = report_config["format"]

        if report_format == "md":
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

        # Markdown 생성
        md_lines = [
            "# Commitly 작업 보고서",
            "",
            f"**기간:** {overview['period']['from']} ~ {overview['period']['to']}",
            "",
            "## 개요 (Overview)",
            "",
            f"- 총 커밋 수: {overview['total_commits']}개",
            f"- Push 성공: {overview['total_pushes']}개",
            f"- Slack 피드백 매칭: {overview['total_slack_matches']}개",
            "",
            "## 커밋 요약",
            "",
        ]

        for i, commit in enumerate(commits, 1):
            md_lines.extend([
                f"### {i}. {commit['commit_message']}",
                "",
                f"- **SHA:** `{commit['commit_sha']}`",
                f"- **Push 여부:** {'✓' if commit['pushed'] else '✗'}",
                f"- **일시:** {commit['timestamp']}",
                "",
            ])

        # Slack 피드백
        if slack_matches:
            md_lines.extend([
                "## Slack 피드백",
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

        # LLM 개선 제안 (선택적)
        llm_client = self.run_context.get("llm_client")

        if llm_client:
            try:
                suggestions = llm_client.generate_improvement_suggestions(summary_data)
                md_lines.extend([
                    "## 향후 개선 제안",
                    "",
                    suggestions,
                    "",
                ])
            except Exception:
                pass

        # 파일 저장
        output_dir = Path(report_config["output_path"])
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"commitly_report_{timestamp}.md"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return report_path
