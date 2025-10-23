# Commitly Docker 가이드

**작성일**: 2025-10-23
**Docker 버전**: 20.10+
**Docker Compose 버전**: 2.0+

---

## 📋 개요

Commitly는 멀티 스테이지 Docker 빌드를 지원하여 **개발, 테스트, 프로덕션** 환경에서 모두 사용할 수 있습니다.

### Docker 이미지 구조

```
Dockerfile (멀티 스테이지)
├── base              - Python 3.11 기본 환경
├── dependencies      - 의존성 설치 (중간 레이어)
├── dev               - 개발 환경 (테스트 도구 포함)
├── test              - 테스트 환경 (pytest 자동 실행)
├── production        - 프로덕션 환경 (최소 크기, ~500MB)
└── docs              - 문서 생성 환경
```

### Docker Compose 구성

```
docker-compose.yml (기본 프로덕션)
├── commitly          - Commitly 메인 서비스
├── postgres          - PostgreSQL 데이터베이스
├── redis             - Redis 캐시
└── slack-webhook     - Slack 프록시 (선택)

docker-compose.dev.yml (개발 환경)
├── commitly:dev      - 소스 코드 바인드 마운트
├── postgres          - 상세 로깅
├── redis             - 모든 포트 노출
└── pgAdmin           - DB 관리 도구

docker-compose.test.yml (테스트 환경)
├── commitly:test     - pytest 자동 실행
├── postgres          - 테스트 DB
├── redis             - 테스트 인스턴스
└── test-reporter     - 결과 리포팅
```

---

## 🚀 빠른 시작

### 전제 조건

```bash
# Docker 설치 확인
docker --version
# Docker version 20.10+

# Docker Compose 설치 확인
docker-compose --version
# Docker Compose version 2.0+
```

### 환경 파일 설정

```bash
# .env 파일 생성
cat > .env << EOF
# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Database
DB_USER=commitly
DB_PASSWORD=commitly123
DB_NAME=commitly_db

# Redis
REDIS_PASSWORD=redis123

# Slack (선택사항)
SLACK_TOKEN=xoxb-your-token
SLACK_CHANNEL=commits
EOF
```

### 프로덕션 배포

```bash
# 이미지 빌드
docker build -t commitly:latest .

# 또는 docker-compose 사용
docker-compose up -d

# 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs -f commitly
```

---

## 🛠️ 개발 환경 설정

### 개발 환경 시작

```bash
# 개발 환경 실행
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# 접속 포트
- Commitly: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- pgAdmin: http://localhost:5050 (admin@commitly.local / admin123)
```

### 소스 코드 수정

개발 환경에서는 **소스 코드가 호스트에서 자동으로 마운트**되므로 바로 반영됩니다.

```bash
# 컨테이너 진입
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec commitly bash

# Commitly 명령 실행
poetry run commitly init
poetry run commitly --help

# pytest 실행
poetry run pytest tests/ -v
```

### 데이터베이스 초기화

```bash
# PostgreSQL 재초기화
docker-compose down -v postgres

# 초기화 스크립트가 있으면 자동 실행
docker-compose up postgres
```

---

## 🧪 테스트 실행

### 테스트 환경 실행

```bash
# 테스트 실행 (자동으로 종료됨)
docker-compose -f docker-compose.yml -f docker-compose.test.yml up \
  --abort-on-container-exit

# 결과 확인
ls test_results/
ls coverage_reports/
```

### 커버리지 리포트 생성

```bash
# 테스트 실행 후 커버리지 리포트 확인
cat coverage_reports/coverage.xml

# HTML 리포트 (로컬에서 생성하면 더 쉬움)
poetry run pytest --cov=src/commitly --cov-report=html tests/
```

### 특정 테스트 실행

```bash
# 컨테이너 진입
docker-compose -f docker-compose.yml -f docker-compose.test.yml exec commitly bash

# 특정 테스트 파일 실행
poetry run pytest tests/test_clone_agent.py -v

# 특정 테스트 함수 실행
poetry run pytest tests/test_clone_agent.py::test_clone_agent_execution -v
```

---

## 📦 Docker 빌드 옵션

### 개발 이미지 빌드

```bash
# 개발 환경 이미지
docker build --target dev -t commitly:dev .

# 실행
docker run -it \
  -v $(pwd)/src:/app/src \
  -v $(pwd)/.env:/app/.env \
  commitly:dev \
  poetry run commitly --help
```

### 테스트 이미지 빌드

```bash
# 테스트 환경 이미지
docker build --target test -t commitly:test .

# 실행 (pytest 자동 실행)
docker run \
  -v $(pwd)/tests:/app/tests \
  commitly:test
```

### 프로덕션 이미지 빌드

```bash
# 프로덕션 이미지 (최소 크기)
docker build --target production -t commitly:latest .

# 이미지 크기 확인
docker images | grep commitly

# 실행
docker run --rm \
  -v ~/.commitly:/app/.commitly \
  -v $(pwd)/.env:/app/.env \
  commitly:latest \
  status
```

### 빌드 빌더 캐시 (속도 최적화)

```bash
# BuildKit 활성화 (더 빠른 빌드)
export DOCKER_BUILDKIT=1

# 캐시와 함께 빌드
docker build --target production -t commitly:latest .

# 캐시 초기화 후 빌드
docker build --no-cache --target production -t commitly:latest .
```

---

## 🗄️ 데이터베이스 관리

### PostgreSQL 초기화

```bash
# 초기화 스크립트 생성 (선택사항)
mkdir -p scripts

cat > scripts/init-db.sql << 'EOF'
-- 테스트용 테이블 생성
CREATE TABLE IF NOT EXISTS test_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 샘플 데이터 삽입
INSERT INTO test_table (name) VALUES ('Sample Data') ON CONFLICT DO NOTHING;
EOF

# 데이터베이스 재시작 (스크립트 자동 실행)
docker-compose down -v postgres
docker-compose up postgres
```

### 데이터베이스 접속

```bash
# psql 접속
docker-compose exec postgres psql -U commitly -d commitly_db

# SQL 쿼리 실행
SELECT * FROM pg_tables WHERE schemaname != 'pg_catalog';
```

### 데이터 백업

```bash
# 데이터베이스 덤프
docker-compose exec postgres pg_dump -U commitly -d commitly_db > backup.sql

# 복원
docker-compose exec -T postgres psql -U commitly -d commitly_db < backup.sql
```

---

## 📊 모니터링 및 로깅

### 로그 확인

```bash
# 실시간 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f commitly

# 최근 100줄 로그
docker-compose logs --tail=100 commitly

# 타임스탬프 포함
docker-compose logs -f --timestamps commitly
```

### 성능 모니터링

```bash
# 컨테이너 리소스 사용량
docker stats

# 실시간 모니터링
docker stats --no-stream

# 상세 정보
docker inspect commitly | grep -A 20 Resources
```

### 헬스 체크

```bash
# 컨테이너 상태 확인
docker-compose ps

# 헬스 체크 상태 보기
docker inspect --format='{{.State.Health.Status}}' commitly

# 헬스 체크 이력
docker inspect commitly | grep -A 30 Health
```

---

## 🔧 문제 해결

### 컨테이너 시작 실패

```bash
# 상세 로그 확인
docker-compose logs commitly

# 컨테이너 재시작
docker-compose restart commitly

# 강제 재빌드
docker-compose up --build commitly
```

### 포트 충돌

```bash
# 포트 사용 중인 프로세스 확인
lsof -i :8000

# 포트 변경 (docker-compose.yml에서)
ports:
  - "8001:8000"  # 호스트:컨테이너

# 또는 환경 변수로 변경
COMMITLY_PORT=8001 docker-compose up
```

### 디스크 공간 부족

```bash
# 미사용 이미지/볼륨 정리
docker system prune

# 강제 정리 (주의!)
docker system prune -a --volumes
```

### 데이터베이스 연결 오류

```bash
# PostgreSQL 상태 확인
docker-compose logs postgres

# 데이터베이스 접속 테스트
docker-compose exec postgres pg_isready -U commitly

# 네트워크 확인
docker-compose logs redis

# 컨테이너 재시작
docker-compose restart postgres redis
```

### 메모리 부족

```bash
# 리소스 제한 확인 (docker-compose.yml)
resources:
  limits:
    cpus: '2'
    memory: 2G

# 메모리 할당 증가
docker update --memory 4G commitly

# 또는 docker-compose.override.yml 생성
cat > docker-compose.override.yml << EOF
version: '3.9'
services:
  commitly:
    resources:
      limits:
        memory: 4G
EOF
```

---

## 📂 파일 구조

```
.
├── Dockerfile                    # 멀티 스테이지 빌드
├── docker-compose.yml            # 프로덕션 스택
├── docker-compose.dev.yml        # 개발 환경 오버라이드
├── docker-compose.test.yml       # 테스트 환경 오버라이드
├── .dockerignore                 # 빌드에서 제외할 파일
├── .env                          # 환경 변수 (gitignore)
│
├── src/commitly/                 # 소스 코드
├── tests/                        # 테스트 코드
├── config.yaml                   # 설정 파일
│
├── data/                         # 데이터 (volume)
│   ├── .commitly/                # Commitly 데이터
│   └── .env                      # 환경 파일 복사본
│
├── hub_repos/                    # Hub 저장소 (volume, 대용량)
│
├── scripts/
│   └── init-db.sql              # DB 초기화 스크립트
│
├── nginx/
│   └── slack-webhook.conf       # Slack 프록시 설정 (선택)
│
├── test_results/                # 테스트 결과 (자동 생성)
└── coverage_reports/            # 커버리지 리포트 (자동 생성)
```

---

## 🌐 네트워크

### 컨테이너 간 통신

```yaml
# 같은 네트워크의 컨테이너는 서비스명으로 통신
# 예: commitly 컨테이너에서 postgres 접속
postgresql://commitly:password@postgres:5432/commitly_db
```

### 외부 네트워크 접속

```bash
# 호스트에서 컨테이너 접속
psql -h localhost -U commitly -d commitly_db

# 컨테이너에서 호스트 접속 (Linux)
# 호스트의 IP를 host.docker.internal로 사용 (Mac/Windows)
```

---

## 🔐 보안

### 환경 변수 관리

```bash
# .env 파일은 .gitignore에 포함
echo ".env" >> .gitignore
echo "*.env.local" >> .gitignore

# 프로덕션에서는 Docker Secrets 사용 (권장)
echo "sk-prod-key" | docker secret create openai_api_key -
```

### 이미지 보안 스캔

```bash
# Docker Scout로 취약점 스캔
docker scout cves commitly:latest

# Trivy로 스캔 (별도 설치 필요)
trivy image commitly:latest
```

### 권한 관리

```bash
# 컨테이너는 non-root 사용자(commitly:1000)로 실행
# Dockerfile 참고: RUN useradd -m -u 1000 commitly
```

---

## 📤 레지스트리에 푸시

```bash
# Docker Hub에 푸시
docker tag commitly:latest yourusername/commitly:latest
docker push yourusername/commitly:latest

# 비공개 레지스트리
docker tag commitly:latest registry.example.com/commitly:latest
docker login registry.example.com
docker push registry.example.com/commitly:latest
```

---

## 🔄 CI/CD 통합

### GitHub Actions 예시

```yaml
# .github/workflows/docker.yml
name: Docker Build & Push

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: docker/setup-buildx-action@v2
      - uses: docker/build-push-action@v4
        with:
          target: production
          push: true
          tags: yourusername/commitly:latest
```

---

## 📚 추가 명령어

```bash
# 이미지 정보 확인
docker images commitly
docker inspect commitly:latest

# 컨테이너 진입
docker-compose exec commitly bash

# 원샷 명령 실행
docker-compose exec commitly commitly status

# 컨테이너 정리
docker-compose down
docker-compose down -v  # 볼륨까지 삭제

# 네트워크 확인
docker network ls
docker network inspect commitly-network

# 볼륨 확인
docker volume ls
docker volume inspect commitly_postgres_data
```

---

## 🎯 모범 사례

1. **버전 고정**: 베이스 이미지 버전을 고정 (`python:3.11-slim` ✅, `python:3.11` ❌)
2. **레이어 최소화**: 명령어 병합으로 레이어 수 감소
3. **캐시 활용**: 자주 변경되지 않는 부분을 먼저 배치
4. **보안**: Non-root 사용자로 실행, 시크릿 관리
5. **헬스 체크**: 모든 서비스에 헬스 체크 추가
6. **리소스 제한**: CPU/메모리 제한으로 무분별한 사용 방지
7. **로깅**: 구조화된 로그 사용

---

**마지막 업데이트**: 2025-10-23
**작성자**: Claude Code
