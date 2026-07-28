# Docker 배포

라즈베리파이에서 `gaon-climate-edge`를 컨테이너로 실행하기 위한 Docker 구성입니다.

## 파일

- `Dockerfile`: Python 런타임과 DHT22/GPIO(libgpiod) 관련 의존성을 포함한 이미지 정의
- `compose.yml`: 라즈베리파이 GPIO 장치 접근 권한과 재시작 정책을 포함한 실행 구성
- `deploy.sh`: 라즈베리파이에서 git clone/pull, Docker 빌드, 컨테이너 실행까지 처리하는 배포 스크립트

## 스크립트 배포

라즈베리파이에서 처음 배포할 때는 아래 명령을 실행합니다.
기본 설치 경로는 `$HOME/gaon-climate-edge`입니다.

```bash
curl -fsSL https://raw.githubusercontent.com/doublejkim/gaon-climate-edge/main/docker/deploy.sh -o /tmp/gaon-climate-deploy.sh
chmod +x /tmp/gaon-climate-deploy.sh
/tmp/gaon-climate-deploy.sh test
```

이미 `$HOME/gaon-climate-edge`가 있으면 스크립트가 `git pull --ff-only`로 갱신한 뒤 Docker 이미지를 다시 빌드하고 컨테이너를 재시작합니다.

설치 경로 또는 브랜치를 바꾸려면 환경변수를 지정합니다.

```bash
APP_DIR=/opt/gaon-climate-edge BRANCH=main /tmp/gaon-climate-deploy.sh test
```

## 실행 모드

`deploy.sh`의 첫 번째 인자로 모드를 지정합니다(`test` / `dummy` / `run`, 기본 `run`).

- `test`: 센서값을 읽어 로그로만 출력합니다. 서버로 전송하지 않습니다.
- `dummy`: 고정 더미값을 서버로 전송합니다. `api_key`/`device_key`가 필요합니다.
- `run`: 실제 센서값을 서버로 전송합니다. `api_key`/`device_key`가 필요합니다.

```bash
/tmp/gaon-climate-deploy.sh test
/tmp/gaon-climate-deploy.sh run
```

배포 전 `config/.env`가 없으면 스크립트가 `config/.env.example`을 복사하고 종료합니다. `SERVER_URL`을 실제 주소로 설정한 뒤 다시 실행합니다.

```bash
cd ~/gaon-climate-edge
cp config/.env.example config/.env
# config/.env의 SERVER_URL을 수정
```

로그를 확인합니다.

```bash
cd ~/gaon-climate-edge
CLIMATE_MODE=run docker compose -f docker/compose.yml logs -f
```

파일 로그는 호스트의 `log/` 디렉토리에 남고 컨테이너에서는 `/app/log`로 마운트됩니다.
Docker 실행 시 호스트의 `/etc/localtime`을 마운트하므로 로그 시간은 라즈베리파이 로컬타임을 따릅니다.

## 디바이스 등록 (claim)

`run`/`dummy` 모드는 `config/.env`에 `api_key`와 `device_key`가 모두 있어야 합니다.
첫 등록은 `deploy.sh`의 두 번째 인자로 claim code를 전달해 수행합니다.

```bash
/tmp/gaon-climate-deploy.sh run <claim_code>
```

스크립트가 일회성 컨테이너로 `POST {SERVER_URL}{server.claim_endpoint}`를 호출하고, 성공하면 응답의 `api_key`/`device.device_key`를 `config/.env`에 저장한 뒤 컨테이너를 기동합니다.

수동으로 등록하려면 아래처럼 실행합니다.

```bash
cd ~/gaon-climate-edge
docker compose -f docker/compose.yml run --rm climate-agent --mode run --claim-code <claim_code>
```

## 수동 실행

```bash
cd ~/gaon-climate-edge
cp config/.env.example config/.env   # 최초 1회, SERVER_URL 설정
CLIMATE_MODE=run docker compose -f docker/compose.yml up -d --build
```

기본값은 `run` 모드입니다. 다른 모드는 `CLIMATE_MODE`로 지정합니다.

```bash
CLIMATE_MODE=test docker compose -f docker/compose.yml up -d --build
```

중지하려면 아래 명령을 실행합니다.

```bash
docker compose -f docker/compose.yml down
```

## 파일 로그

로그 파일은 프로젝트의 `log/` 디렉토리에 생성됩니다.

파일명 형식은 아래와 같습니다.

```text
edge.YYYYMMDD.HH.log
```

예시:

```text
edge.20260503.09.log
edge.20260503.17.log
```

시간은 24시간제이며 한 자리 숫자는 `09`처럼 두 자리로 기록합니다.
로그 파일은 시간 단위로 바뀌고, `config/config.yml`의 `logging.retention_days`를 초과한 `edge.*.*.log` 파일은 앱 시작 및 시간 변경 시 자동 삭제됩니다. 기본값은 `7`(7일)입니다.

```yaml
logging:
  retention_days: 7
```

## 문제 해결

GPIO 장치(`/dev/gpiochip0`)가 없으면 `compose.yml`의 `devices` 항목을 환경에 맞게 조정합니다(보드에 따라 gpiochip 번호가 다를 수 있습니다).
DHT22 데이터 핀을 연결한 GPIO 번호를 `config/config.yml`의 `sensor.board_pin`(예: `D4` = GPIO4)에 맞춥니다.

컨테이너 내부 `/app/log`에는 파일이 있는데 호스트에서 안 보인다면 다른 경로가 마운트되었을 수 있습니다.

```bash
docker inspect gaon-climate-edge --format '{{ range .Mounts }}{{ println .Source "->" .Destination }}{{ end }}'
```
