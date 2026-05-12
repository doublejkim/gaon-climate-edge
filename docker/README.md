# Docker 배포

라즈베리파이에서 `gaon-climate-edge`를 컨테이너로 실행하기 위한 Docker 구성입니다.

## 파일

- `Dockerfile`: Python 런타임과 DHT22/GPIO 관련 의존성을 포함한 이미지 정의
- `compose.yml`: 라즈베리파이 GPIO 장치 접근 권한과 재시작 정책을 포함한 실행 구성
- `deploy.sh`: 라즈베리파이에서 git clone/pull, Docker 빌드, 컨테이너 실행까지 처리하는 배포 스크립트

## 스크립트 배포

라즈베리파이에서 처음 배포할 때는 아래 명령을 실행합니다.
기본 설치 경로는 `$HOME/gaon-climate-edge`입니다.

```bash
curl -fsSL https://raw.githubusercontent.com/doublejkim/gaon-climate-edge/main/docker/deploy.sh -o /tmp/gaon-climate-deploy.sh
chmod +x /tmp/gaon-climate-deploy.sh
/tmp/gaon-climate-deploy.sh local
```

이미 `$HOME/gaon-climate-edge`가 있으면 스크립트가 `git pull --ff-only`로 갱신한 뒤 Docker 이미지를 다시 빌드하고 컨테이너를 재시작합니다.

설치 경로 또는 브랜치를 바꾸려면 환경변수를 지정합니다.

```bash
APP_DIR=/opt/gaon-climate-edge BRANCH=main /tmp/gaon-climate-deploy.sh local
```

### local 환경

센서 연결과 로그 확인용 환경입니다.
서버로 데이터를 전송하지 않으며 `config/.env`가 없어도 실행할 수 있습니다.

```bash
/tmp/gaon-climate-deploy.sh local
```

로그를 확인합니다.

```bash
cd ~/gaon-climate-edge
CLIMATE_MODE=local docker compose -f docker/compose.yml logs -f
```

파일 로그는 호스트의 `log/` 디렉토리에 남습니다.
컨테이너에서는 `/app/log`로 마운트됩니다.
`local` 모드는 `DEBUG`, `INFO`, `WARNING`, `ERROR` 레벨 로그를 모두 기록합니다.
Docker 실행 시 호스트의 `/etc/localtime`을 컨테이너에 마운트하므로 로그의 `asctime`은 라즈베리파이 시스템 로컬타임을 따릅니다.

마운트된 호스트 경로는 배포 스크립트 실행 마지막에 출력됩니다.
컨테이너가 실제로 어떤 경로를 마운트했는지는 아래처럼 확인합니다.

```bash
docker inspect gaon-climate-edge --format '{{ range .Mounts }}{{ println .Source "->" .Destination }}{{ end }}'
```

라즈베리파이에서 소스가 변경되었거나 Docker 의존성이 바뀌었을 때도 같은 명령을 다시 실행하면 됩니다.
스크립트가 `git pull --ff-only` 후 이미지를 다시 빌드하고 컨테이너를 재시작합니다.

```bash
cd ~/gaon-climate-edge
./docker/deploy.sh local
```

### prod 환경

운영 서버로 데이터를 전송하는 환경입니다.
먼저 저장소를 받은 뒤 환경 파일을 준비합니다.

```bash
/tmp/gaon-climate-deploy.sh local
cd ~/gaon-climate-edge
cp config/.env.example config/.env
```

`config/.env`에 실제 서버 주소와 인증키를 설정합니다.

```bash
CLIMATE_SERVER_URL=https://example.com
CLIMATE_API_KEY=
REQUEST_TIMEOUT_SECONDS=10
```

그 다음 prod 모드로 배포합니다.

```bash
/tmp/gaon-climate-deploy.sh prod
```

prod 로그를 확인합니다.

```bash
cd ~/gaon-climate-edge
CLIMATE_MODE=prod docker compose -f docker/compose.yml logs -f
```

`prod` 모드는 `INFO`, `WARNING`, `ERROR` 레벨 로그를 기록합니다.
디바이스 키 파일은 기본적으로 호스트의 `/home/doublej/.config/gaon-climate/device-key`에 저장되고, 컨테이너에서는 `/root/.config/gaon-climate/device-key`로 마운트됩니다.
다른 사용자 계정 경로를 쓰려면 `DEVICE_CONFIG_DIR=/home/다른계정/.config/gaon-climate ./docker/deploy.sh prod`처럼 실행하거나 `docker/deploy.sh`의 `DEVICE_CONFIG_DIR` 기본값을 변경합니다.
키 파일이 없으면 `config/config.yml`의 `server.registration_endpoint`로 등록 요청을 보냅니다.
등록 요청이 `401`, `409`, `5xx` 응답을 받으면 로그를 남기고 프로그램을 종료합니다.
등록 실패는 정상 종료 코드로 종료되므로 Docker가 같은 등록 실패를 무한 반복하지 않습니다.

## 수동 실행

`prod` 모드로 실행할 예정이라면 프로젝트 루트에서 환경 파일을 준비합니다.

```bash
cp config/.env.example config/.env
```

`config/.env`와 `config/config.yml`을 라즈베리파이 환경에 맞게 수정한 뒤 실행합니다.
`local` 모드는 `config/.env`가 없어도 실행할 수 있습니다.

```bash
docker compose -f docker/compose.yml up -d --build
```

기본값은 `local` 모드입니다. 운영 서버로 전송하려면 `CLIMATE_MODE=prod`를 함께 지정합니다.

```bash
CLIMATE_MODE=prod docker compose -f docker/compose.yml up -d --build
```

로그는 아래 명령으로 확인합니다.

```bash
docker compose -f docker/compose.yml logs -f
```

중지하려면 아래 명령을 실행합니다.

```bash
docker compose -f docker/compose.yml down
```

## 파일 로그

로그 파일은 프로젝트의 `log/` 디렉토리에 생성됩니다.
Docker 실행 시 호스트의 `log/` 디렉토리가 컨테이너의 `/app/log`로 마운트됩니다.

파일명 형식은 아래와 같습니다.

```text
gaon-climate-edge.YYYYMMDD.HH.log
```

예시는 아래와 같습니다.

```text
gaon-climate-edge.20260503.09.log
gaon-climate-edge.20260503.17.log
```

시간은 24시간제이며 한 자리 숫자는 `09`처럼 두 자리로 기록합니다.
로그 본문 시간은 라즈베리파이 시스템 로컬타임으로 기록됩니다.
로그 파일은 시간 단위로 바뀌고, `config/config.yml`의 `logging.retention_days`를 초과한 `gaon-climate-edge.*.*.log` 파일은 앱 시작 및 시간 변경 시 자동 삭제됩니다.
기본값은 `3`이며 3일, 즉 72시간 보관을 의미합니다.

```yaml
logging:
  retention_days: 3
```

## 디바이스 등록

`prod` 모드에서 디바이스 키 파일이 없으면 서버에 디바이스 등록을 요청합니다.

키 파일 위치:

```text
/home/doublej/.config/gaon-climate/device-key
```

등록 요청 URL:

```text
{CLIMATE_SERVER_URL}{server.registration_endpoint}
```

기본값은 아래와 같습니다.

```yaml
server:
  registration_endpoint: /clidmate
```

등록 요청 payload:

```json
{
  "device_name": "gaon-climate-edge-01"
}
```

등록 응답은 `device_key`, `deviceKey`, `key` 필드를 가진 JSON 또는 plain text 키를 지원합니다.

## 문제 해결

라즈베리파이 5처럼 `bcm2712` GPIO를 사용하는 환경에서 아래 오류가 나면 Docker 이미지에 `lgpio` Python 모듈이 없는 상태입니다.

```text
ModuleNotFoundError: No module named 'lgpio'
```

최신 소스를 받은 뒤 이미지를 다시 빌드합니다.

```bash
cd ~/gaon-climate-edge
./docker/deploy.sh local
```

컨테이너 내부 `/app/log`에는 파일이 있는데 호스트에서 안 보인다면, 다른 프로젝트 경로가 마운트되었을 가능성이 큽니다.
아래 명령의 `/app/log` 왼쪽 경로를 확인합니다.

```bash
docker inspect gaon-climate-edge --format '{{ range .Mounts }}{{ println .Source "->" .Destination }}{{ end }}'
```
