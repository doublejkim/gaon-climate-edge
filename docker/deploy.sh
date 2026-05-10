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
MODE="${1:-local}"

if [ "$MODE" != "local" ] && [ "$MODE" != "prod" ]; then
    echo "Usage: $0 [local|prod]"
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
# Device key storage on the Raspberry Pi host.
# Change this path when the service should use another Linux account.
# The compose file mounts this host directory to /root/.config/gaon-climate
# because the Python process runs as root inside the container.
DEVICE_CONFIG_DIR="${DEVICE_CONFIG_DIR:-/home/doublej/.config/gaon-climate}"
mkdir -p "$DEVICE_CONFIG_DIR"
export APP_DEVICE_CONFIG_DIR="$DEVICE_CONFIG_DIR"

if [ "$MODE" = "prod" ]; then
    if [ ! -f config/.env ]; then
        cp config/.env.example config/.env
        echo "Created config/.env from config/.env.example."
        echo "Edit config/.env and set CLIMATE_SERVER_URL before running prod mode again."
        exit 1
    fi

    if ! grep -Eq '^CLIMATE_SERVER_URL=https?://[^[:space:]]+' config/.env; then
        echo "config/.env must contain CLIMATE_SERVER_URL for prod mode."
        exit 1
    fi

    if grep -Eq '^CLIMATE_SERVER_URL=https://example\.com/?$' config/.env; then
        echo "config/.env still uses the example CLIMATE_SERVER_URL."
        exit 1
    fi
fi

echo "Building and starting gaon-climate-edge in $MODE mode"
export CLIMATE_MODE="$MODE"
compose -f docker/compose.yml up -d --build --force-recreate

echo "Done. Follow logs with:"
echo "  cd $APP_DIR && CLIMATE_MODE=$MODE $COMPOSE_DISPLAY -f docker/compose.yml logs -f"
echo "Log files are written to:"
echo "  $APP_DIR/log"
echo "Mounted container log path:"
echo "  $APP_LOG_DIR -> /app/log"
echo "Device key file path:"
echo "  $APP_DEVICE_CONFIG_DIR/device-key"
