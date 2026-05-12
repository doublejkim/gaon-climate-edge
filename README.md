# Gaon Climate Edge

DHT22 온습도 센서 값을 라즈베리파이에서 주기적으로 수집하는 에지 프로그램입니다.
기본 실행 모드는 `local`이며, `prod` 모드에서만 실제 서버로 측정값을 전송합니다.

## 사전 준비

라즈베리파이에 DHT22 센서를 연결합니다.

- 기본 GPIO 핀은 `D4`입니다.
- 핀 설정은 `config/config.yml`의 `sensor.board_pin`에서 변경할 수 있습니다.
- 현재 센서 코드는 `docs/sample_dht.py`와 동일하게 `adafruit_dht.DHT22(..., use_pulseio=False)`를 사용합니다.

파이썬 패키지를 설치합니다.

```bash
pip install -r requirements.txt
```

## 설정 파일

프로그램 설정은 `config/config.yml`에서 관리합니다.

- `sensor`: DHT22 센서 핀과 pulseio 사용 여부
- `collection.interval_seconds`: 온습도 수집 주기
- `collection.max_temperature_delta_c`: 직전 정상 온도와 현재 온도의 허용 차이
- `collection.retry_limit`: 이상값 또는 센서 읽기 실패 시 재시도 횟수
- `collection.retry_delay_seconds`: 재시도 사이 대기 시간
- `server.endpoint`: 서버로 전송할 API 경로
- `server.registration_endpoint`: 디바이스 키 파일이 없을 때 등록 요청을 보낼 API 경로
- `logging.retention_days`: 로그 파일 보관 일수
- `device.name`: 디바이스 등록 요청에 포함할 로컬 장비 이름

서버 접속 정보는 `config/.env`에서 관리합니다.
이 파일은 `.gitignore`에 등록되어 있으므로 git으로 관리되지 않습니다.

`config/.env.example`을 참고해서 `config/.env`를 생성합니다.

```bash
CLIMATE_SERVER_URL=https://example.com
CLIMATE_API_KEY=
REQUEST_TIMEOUT_SECONDS=10
```

## 실행 모드

실행 모드는 `--mode` 옵션으로 지정합니다.
옵션을 생략하면 `local` 모드로 실행됩니다.

```bash
python3 src/climate_agent.py
python3 src/climate_agent.py --mode local
python3 src/climate_agent.py --mode prod
```

## Docker로 라즈베리파이에 배포

라즈베리파이에서 직접 Python 환경을 맞추지 않고 Docker로 실행할 수 있습니다.
Docker 관련 파일은 `docker/` 디렉토리에 있습니다.

- `docker/Dockerfile`: 실행 이미지 정의
- `docker/compose.yml`: GPIO 장치 접근 권한, 설정 파일 마운트, 재시작 정책을 포함한 Compose 구성
- `docker/deploy.sh`: 라즈베리파이에서 git clone/pull, Docker 빌드, 컨테이너 실행까지 처리하는 배포 스크립트
- `docker/README.md`: Docker 실행 요약 문서

### 1. 라즈베리파이에 Docker 설치

라즈베리파이에서 Docker와 Docker Compose v2가 필요합니다.

```bash
docker --version
docker compose version
```

위 명령이 동작하지 않으면 Docker를 먼저 설치합니다.

### 2. 배포 스크립트 실행

라즈베리파이에서 아래 명령으로 저장소를 받고, 최신 코드로 갱신하고, Docker 이미지를 빌드한 뒤 컨테이너를 실행할 수 있습니다.
저장소 주소는 `https://github.com/doublejkim/gaon-climate-edge.git`입니다.

```bash
curl -fsSL https://raw.githubusercontent.com/doublejkim/gaon-climate-edge/main/docker/deploy.sh -o /tmp/gaon-climate-deploy.sh
chmod +x /tmp/gaon-climate-deploy.sh
/tmp/gaon-climate-deploy.sh local
```

기본 설치 경로는 `$HOME/gaon-climate-edge`입니다.
이미 저장소가 있으면 스크립트가 `git pull --ff-only`로 갱신합니다.

설치 경로를 바꾸려면 `APP_DIR`을 지정합니다.

```bash
APP_DIR=/opt/gaon-climate-edge /tmp/gaon-climate-deploy.sh local
```

### 3. local 환경

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

라즈베리파이에서 소스 또는 Docker 의존성이 변경된 이후에는 배포 스크립트를 다시 실행하면 됩니다.
스크립트가 `git pull --ff-only` 후 이미지를 다시 빌드하고 컨테이너를 재시작합니다.

```bash
cd ~/gaon-climate-edge
./docker/deploy.sh local
```

### 4. prod 환경

운영 서버로 데이터를 전송하는 환경입니다.
먼저 `config/.env` 파일을 준비합니다.

`prod` 모드로 실행할 예정이라면 프로젝트 루트에서 `.env` 파일을 만듭니다.

```bash
cp config/.env.example config/.env
```

`local` 모드는 `config/.env`가 없어도 실행할 수 있습니다.
`prod` 모드로 서버에 전송하려면 `config/.env`에 실제 서버 주소를 넣습니다.

```bash
CLIMATE_SERVER_URL=https://example.com
CLIMATE_API_KEY=
REQUEST_TIMEOUT_SECONDS=10
```

센서 GPIO 핀, 수집 주기, 로컬 장비 이름은 `config/config.yml`에서 수정합니다.
Docker 실행 시 `config/` 디렉토리가 컨테이너의 `/app/config`로 읽기 전용 마운트됩니다.
디바이스 키 파일은 기본적으로 호스트의 `/home/doublej/.config/gaon-climate/device-key`에 저장되고, 컨테이너에서는 `/root/.config/gaon-climate/device-key`로 마운트됩니다.
다른 사용자 계정 경로를 쓰려면 `DEVICE_CONFIG_DIR=/home/다른계정/.config/gaon-climate ./docker/deploy.sh prod`처럼 실행하거나 `docker/deploy.sh`의 `DEVICE_CONFIG_DIR` 기본값을 변경합니다.

prod 모드로 배포합니다.

```bash
/tmp/gaon-climate-deploy.sh prod
```

`prod` 모드는 `INFO`, `WARNING`, `ERROR` 레벨 로그를 기록합니다.

### 5. 수동 local 모드 실행

기본 Docker 실행 모드는 `local`입니다.
센서 값은 읽지만 서버로 POST 요청을 보내지 않습니다.

```bash
docker compose -f docker/compose.yml up -d --build
```

로그를 확인합니다.

```bash
docker compose -f docker/compose.yml logs -f
```

### 6. 수동 prod 모드 실행

운영 서버로 측정값을 전송하려면 `CLIMATE_MODE=prod`를 함께 지정합니다.

```bash
CLIMATE_MODE=prod docker compose -f docker/compose.yml up -d --build
```

### 7. 중지 및 재시작

컨테이너를 중지합니다.

```bash
docker compose -f docker/compose.yml down
```

설정만 바꾼 뒤 다시 시작할 때는 아래 명령을 사용할 수 있습니다.

```bash
docker compose -f docker/compose.yml restart
```

### GPIO 권한 참고

DHT22 센서 라이브러리는 라즈베리파이의 GPIO 장치에 접근해야 합니다.
`docker/compose.yml`은 이를 위해 `privileged: true`와 `/dev/gpiomem`, `/dev/mem` 장치 매핑을 포함합니다.
배포 대상 라즈베리파이에 `/dev/gpiomem`이 없는 경우 `devices` 항목을 환경에 맞게 조정하거나 `privileged: true`만으로 실행되는지 확인합니다.

라즈베리파이 5처럼 `bcm2712` GPIO를 사용하는 환경에서 `ModuleNotFoundError: No module named 'lgpio'`가 발생하면 최신 소스를 받은 뒤 Docker 이미지를 다시 빌드합니다.

```bash
cd ~/gaon-climate-edge
./docker/deploy.sh local
```

### 파일 로그 운영 규칙

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

## local 모드

개발 또는 현장 점검용 모드입니다.

- 기본 실행 모드입니다.
- 센서에서 온도와 습도를 실제로 수집합니다.
- 수집된 값은 로그로 남깁니다.
- 서버 전송 타이밍에도 실제 POST 요청을 보내지 않고, 전송을 건너뛰었다는 로그만 남깁니다.
- `CLIMATE_SERVER_URL`이 없어도 실행할 수 있습니다.

예시:

```bash
python3 src/climate_agent.py --mode local
```

## prod 모드

운영 서버로 데이터를 전송하는 모드입니다.

- 센서에서 온도와 습도를 실제로 수집합니다.
- 정상 수집된 값만 서버로 전송합니다.
- `config/.env`에 `CLIMATE_SERVER_URL`이 반드시 필요합니다.
- `CLIMATE_API_KEY`가 있으면 `Authorization: Bearer ...` 헤더로 함께 전송합니다.
- 실행 시 `/home/doublej/.config/gaon-climate/device-key` 파일을 확인합니다.
- 디바이스 키 파일이 없으면 `server.registration_endpoint`로 등록 요청을 보냅니다.
- 등록 요청이 `401`, `409`, `5xx` 응답을 받으면 로그를 남기고 종료합니다.
- 등록 요청이 `200 OK`이고 응답에서 디바이스 키를 읽으면 키 파일에 저장한 뒤 온습도 전송을 시작합니다.
- 등록 실패는 정상 종료 코드로 종료되므로 Docker가 같은 등록 실패를 무한 반복하지 않습니다.

전송 URL은 아래처럼 만들어집니다.

```text
{CLIMATE_SERVER_URL}/clidmate/{device_key}
```

예시:

```bash
python3 src/climate_agent.py --mode prod
```

## 수집 및 검증 동작

프로그램은 기본적으로 1분마다 온도와 습도를 수집합니다.

1. DHT22 센서에서 현재 온도와 습도를 읽습니다.
2. 직전 정상 온도와 현재 온도의 차이를 계산합니다.
3. 차이가 `collection.max_temperature_delta_c`보다 크면 이상값으로 보고 다시 측정합니다.
4. 재측정은 `collection.retry_limit` 횟수까지만 반복합니다.
5. 정상값으로 판단되면 `local` 모드에서는 로그만 남기고, `prod` 모드에서는 서버로 POST 요청을 보냅니다.

## 서버 전송 payload

`prod` 모드에서 서버로 전송하는 JSON 형식입니다.

```json
{
  "temperature_c": 24.5,
  "humidity": 55.0,
  "measured_at": "2026-05-03T13:00:00"
}
```

`measured_at`은 클라이언트 시스템의 로컬 시간을 사용하며 timezone offset은 포함하지 않습니다.

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

## 도움말

실행 옵션은 아래 명령으로 확인할 수 있습니다.

```bash
python3 src/climate_agent.py --help
```
