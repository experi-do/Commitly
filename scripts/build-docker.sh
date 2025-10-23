#!/usr/bin/env bash

################################################################################
# Commitly Docker 빌드 스크립트
#
# 용도:
#   모든 Docker 이미지 자동 빌드 (dev, test, production)
#   빌드 실패 시 중단 및 에러 리포팅
#
# 사용법:
#   ./scripts/build-docker.sh [stage]
#   ./scripts/build-docker.sh          # 모든 스테이지 빌드
#   ./scripts/build-docker.sh dev      # 개발 이미지만
#   ./scripts/build-docker.sh test     # 테스트 이미지만
#   ./scripts/build-docker.sh prod     # 프로덕션 이미지만
#
# 환경 변수:
#   DOCKER_BUILDKIT=1  (선택) BuildKit 사용 (더 빠른 빌드)
#
################################################################################

set -euo pipefail

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

# 사용법 출력
usage() {
    cat << EOF
사용법: $0 [stage]

Stage 옵션:
  dev        개발 환경 이미지 (모든 도구 포함)
  test       테스트 환경 이미지 (pytest 포함)
  prod       프로덕션 이미지 (최소 크기)
  all        모든 스테이지 빌드 (기본값)

예시:
  $0              # 모든 스테이지 빌드
  $0 dev          # 개발 환경만 빌드
  $0 prod         # 프로덕션만 빌드

환경 변수:
  DOCKER_BUILDKIT=1   BuildKit 활성화 (더 빠른 빌드)
  NO_CACHE=1          캐시 무시하고 빌드
EOF
    exit 1
}

# 사전 체크
check_prerequisites() {
    log_info "사전 조건 확인 중..."

    # Docker 설치 확인
    if ! command -v docker &> /dev/null; then
        log_error "Docker가 설치되지 않았습니다"
        exit 1
    fi

    # Docker 데몬 실행 확인
    if ! docker ps > /dev/null 2>&1; then
        log_error "Docker 데몬이 실행 중이지 않습니다"
        exit 1
    fi

    # Dockerfile 존재 확인
    if [[ ! -f "Dockerfile" ]]; then
        log_error "Dockerfile을 찾을 수 없습니다: $PROJECT_ROOT/Dockerfile"
        exit 1
    fi

    log_success "사전 조건 확인 완료"
}

# 이미지 빌드
build_image() {
    local stage=$1
    local tag=$2

    log_info "빌드 시작: $stage 스테이지"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # BuildKit 활성화 (선택적)
    local docker_buildkit=${DOCKER_BUILDKIT:-0}
    if [[ "$docker_buildkit" == "1" ]]; then
        log_info "BuildKit 활성화"
        export DOCKER_BUILDKIT=1
    fi

    # 캐시 무시 옵션
    local no_cache=""
    if [[ "${NO_CACHE:-0}" == "1" ]]; then
        no_cache="--no-cache"
        log_warning "캐시를 무시하고 빌드합니다"
    fi

    # Docker 빌드 실행
    if docker build \
        --target "$stage" \
        -t "commitly:$tag" \
        -f Dockerfile \
        $no_cache \
        .; then

        log_success "$stage 스테이지 빌드 완료: commitly:$tag"
        return 0
    else
        log_error "$stage 스테이지 빌드 실패"
        return 1
    fi
}

# 이미지 정보 출력
print_image_info() {
    local tag=$1

    echo ""
    log_info "이미지 정보: commitly:$tag"

    # 이미지 크기
    local size=$(docker images commitly:$tag --format "{{.Size}}")
    echo "  크기: $size"

    # 레이어 정보
    local layers=$(docker inspect commitly:$tag --format '{{len .RootFS.Layers}}')
    echo "  레이어: $layers개"

    # 생성 시간
    local created=$(docker inspect commitly:$tag --format '{{.Created}}')
    echo "  생성일: $created"
}

# 빌드 결과 요약
print_summary() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "빌드 완료 요약"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 모든 commitly 이미지 나열
    echo ""
    echo "생성된 이미지:"
    docker images commitly --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

    echo ""
    echo "다음 명령으로 실행할 수 있습니다:"
    echo ""
    echo "  프로덕션:  docker-compose up -d"
    echo "  개발:      docker-compose -f docker-compose.yml -f docker-compose.dev.yml up"
    echo "  테스트:    docker-compose -f docker-compose.yml -f docker-compose.test.yml up"
    echo ""
}

# 메인 실행
main() {
    local stage="${1:-all}"

    # 사용법 출력
    if [[ "$stage" == "-h" ]] || [[ "$stage" == "--help" ]]; then
        usage
    fi

    # 시작 메시지
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Commitly Docker 빌드 스크립트"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "프로젝트: $PROJECT_ROOT"
    echo "빌드 Stage: $stage"
    echo ""

    # 사전 체크
    check_prerequisites

    # 빌드 실행
    case "$stage" in
        dev)
            build_image "dev" "dev" || exit 1
            print_image_info "dev"
            ;;
        test)
            build_image "test" "test" || exit 1
            print_image_info "test"
            ;;
        prod|production)
            build_image "production" "latest" || exit 1
            print_image_info "latest"
            ;;
        all|"")
            # 모든 스테이지 빌드
            build_image "dev" "dev" || exit 1
            print_image_info "dev"

            build_image "test" "test" || exit 1
            print_image_info "test"

            build_image "production" "latest" || exit 1
            print_image_info "latest"
            ;;
        *)
            log_error "알 수 없는 stage: $stage"
            usage
            ;;
    esac

    # 최종 요약
    print_summary

    log_success "모든 빌드가 완료되었습니다!"
}

# 스크립트 실행
main "$@"
