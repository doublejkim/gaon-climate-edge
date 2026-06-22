#!/usr/bin/env sh
set -eu

REPO_URL="${REPO_URL:-https://github.com/doublejkim/gaon-climate-edge.git}"
SCRIPT_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
SCRIPT_APP_DIR="$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)"
if [ -z "${APP_DIR:-}" ]; then
    if [ -d "$SCRIPT_APP_DIR/.git" ]; then
        APP_DIR="$SCRIPT_APP_DIR"
    else
        APP_DIR="$HOME/gaon-climate-edge"
    fi
fi
BRANCH="${BRANCH:-main}"
MODE="${1:-run}"
# 두 번째 인자로 claim code를 주면 첫 실행 등록을 먼저 수행합니다.
CLAIM_CODE="${2:-}"

if [ "$MODE" != "test" ] && [ "$MODE" != "dummy" ] && [ "$MODE" != "run" ]; then
    echo "Usage: $0 [test|dummy|run] [claim_code]"
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "git is required."
    exit 1
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_DISPLAY="docker compose"
    compose() {
        docker compose "$@"
    }
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_DISPLAY="docker-compose"
    compose() {
        docker-compose "$@"
    }
else
    echo "Docker Compose is required. Install Docker Compose v2 or docker-compose."
    exit 1
fi

if [ -d "$APP_DIR/.git" ]; then
    echo "Updating repository in $APP_DIR"
    git -C "$APP_DIR" pull --ff-only
elif [ -e "$APP_DIR" ]; then
    echo "$APP_DIR already exists but is not a git repository."
    exit 1
else
    echo "Cloning $REPO_URL into $APP_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
mkdir -p log
export APP_CONFIG_DIR="$APP_DIR/config"
export APP_LOG_DIR="$APP_DIR/log"

if [ ! -f config/.env ]; then
    cp config/.env.example config/.env
    echo "Created config/.env from config/.env.example."
    echo "Edit config/.env and set SERVER_URL before running again."
    exit 1
fi

if ! grep -Eq '^SERVER_URL=https?://[^[:space:]]+' config/.env; then
    echo "config/.env must contain SERVER_URL."
    exit 1
fi

if grep -Eq '^SERVER_URL=https://example\.com/?$' config/.env; then
    echo "config/.env still uses the example SERVER_URL."
    exit 1
fi

export CLIMATE_MODE="$MODE"

# run/dummy 모드는 등록된 디바이스(api_key/device_key)가 필요합니다.
if [ "$MODE" = "run" ] || [ "$MODE" = "dummy" ]; then
    if [ -n "$CLAIM_CODE" ]; then
        echo "Registering device with claim code"
        compose -f docker/compose.yml build
        compose -f docker/compose.yml run --rm climate-agent --mode run --claim-code "$CLAIM_CODE"
    elif ! grep -Eq '^api_key=.+' config/.env || ! grep -Eq '^device_key=.+' config/.env; then
        echo "config/.env must contain api_key and device_key for $MODE mode."
        echo "Run first-time registration with: $0 $MODE <claim_code>"
        exit 1
    fi
fi

echo "Building and starting gaon-climate-edge in $MODE mode"
compose -f docker/compose.yml up -d --build --force-recreate

echo "Done. Follow logs with:"
echo "  cd $APP_DIR && CLIMATE_MODE=$MODE $COMPOSE_DISPLAY -f docker/compose.yml logs -f"
echo "Log files are written to:"
echo "  $APP_DIR/log"
echo "Mounted container log path:"
echo "  $APP_LOG_DIR -> /app/log"
