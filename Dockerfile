# ==================== Dockerfile - Commitly Multi-Stage Build ====================
#
# 목적: 개발, 테스트, 프로덕션 환경에서 모두 사용 가능한 Docker 이미지 구성
#
# 스테이지:
# 1. base        - Python 기본 환경
# 2. dev         - 개발 환경 (의존성 설치 + 테스트 도구)
# 3. test        - 테스트 환경 (테스트 실행)
# 4. production  - 프로덕션 환경 (최소 크기)
#
# 사용법:
#   개발:     docker build --target dev -t commitly:dev .
#   테스트:   docker build --target test -t commitly:test .
#   프로덕션: docker build --target production -t commitly:latest .
#
# ==================================================================================

# ============================================================================
# Stage 1: BASE - Python 기본 환경
# ============================================================================
FROM python:3.11-slim as base

# 메타데이터
LABEL maintainer="Claude Code <noreply@anthropic.com>"
LABEL description="Commitly - AI-powered multi-agent commit automation system"
LABEL version="1.0"

# 환경 변수
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true \
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

# PATH 설정
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Poetry 설치
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# 작업 디렉토리
WORKDIR /app

# 소유자 설정 (non-root 사용자)
RUN useradd -m -u 1000 commitly && \
    chown -R commitly:commitly /app

# ============================================================================
# Stage 2: DEPENDENCIES - 의존성 설치
# ============================================================================
FROM base as dependencies

# pyproject.toml과 poetry.lock 복사
COPY pyproject.toml poetry.lock* ./

# 의존성 설치
RUN poetry install --no-dev --no-root

# ============================================================================
# Stage 3: DEV - 개발 환경
# ============================================================================
FROM base as dev

LABEL stage="development"

# Poetry와 필요한 모든 의존성 복사 (테스트 포함)
COPY --from=base $POETRY_HOME $POETRY_HOME
COPY --from=base /usr/local/bin/poetry /usr/local/bin/poetry

# 작업 디렉토리
WORKDIR /app

# 의존성 파일 복사
COPY pyproject.toml poetry.lock* ./

# 모든 의존성 설치 (dev 포함)
RUN poetry install

# 소스 코드 복사
COPY . .

# 권한 설정
RUN chown -R commitly:commitly /app

# 사용자 전환
USER commitly

# 진입점
ENTRYPOINT ["poetry", "run"]
CMD ["commitly", "--help"]

# 환경 변수 (개발용)
ENV ENVIRONMENT=development \
    PYTHONUNBUFFERED=1

# ============================================================================
# Stage 4: TEST - 테스트 환경
# ============================================================================
FROM dev as test

LABEL stage="testing"

# 테스트 실행을 위한 작업 디렉토리
WORKDIR /app

# 테스트 데이터 또는 설정이 있으면 복사
COPY tests/ ./tests/
COPY pytest.ini ./

# 진입점: pytest 실행
ENTRYPOINT ["poetry", "run"]
CMD ["pytest", "tests/", "-v", "--cov=src/commitly"]

# ============================================================================
# Stage 5: PRODUCTION - 프로덕션 환경 (최소 크기)
# ============================================================================
FROM base as production

LABEL stage="production"

# dependencies 스테이지에서 가상환경 복사
COPY --from=dependencies $VENV_PATH $VENV_PATH

# 소스 코드만 복사
COPY --chown=commitly:commitly . .

# 사용자 전환
USER commitly

# 볼륨 설정 (Git 저장소, 설정 파일)
VOLUME ["/app/.commitly", "/app/.env"]

# 포트 (WebUI 대시보드용, 향후 추가)
EXPOSE 8000

# 진입점
ENTRYPOINT ["/opt/pysetup/.venv/bin/commitly"]
CMD ["--help"]

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /opt/pysetup/.venv/bin/commitly status || exit 1

# ============================================================================
# Stage 6: DOCS - 문서 생성 환경 (선택사항)
# ============================================================================
FROM base as docs

LABEL stage="documentation"

# 문서 생성 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    texlive-latex-base \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY pyproject.toml poetry.lock* ./
RUN poetry install

# 소스 코드 복사
COPY . .

WORKDIR /app/docs

# 진입점: 문서 생성
ENTRYPOINT ["poetry", "run"]
CMD ["bash", "-c", "ls docs/ && echo 'Documentation ready'"]
