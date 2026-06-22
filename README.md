# Gaon Climate Edge

라즈베리파이에 연결한 **BME280** 온습도 센서 값을 1분마다 수집해 서버로 전송하는 에지 프로그램입니다.

## 사전 준비

라즈베리파이에 BME280 센서를 **I2C**로 연결하고 I2C를 활성화합니다(`raspi-config` → Interface Options → I2C).

- 센서는 forced mode 소프트웨어 타이머로 1분마다 1회 측정합니다.
- BME280 I2C 주소는 보드에 따라 `0x76` 또는 `0x77`이며 `config/config.yml`의 `sensor.i2c_address`에서 변경합니다.

파이썬 패키지를 설치합니다.

```bash
pip install -r requirements.txt
```

## 설정 파일

### config/config.yml

프로그램 동작 설정을 관리합니다.

- `type`: 디바이스 종류. `TEMP_HUMIDITY`(기본) 또는 `MIC`. claim 등록의 `name`/`type`로 전송됩니다.
- `sensor.i2c_address`: BME280 I2C 주소 (`0x76` 또는 `0x77`)
- `collection.interval_seconds`: 수집 주기(기본 60초 = 1분)
- `collection.retry_limit` / `collection.retry_delay_seconds`: 센서 읽기 실패 시 재시도 설정
- `server.climate_endpoint`: 온습도 전송 API 경로 (`/climate/{device_key}`)
- `server.claim_endpoint`: claim 등록 API 경로 (`/devices/claim`)
- `logging.retention_days`: 로그 파일 보관 일수(기본 7)
- `device.location_name`: claim 등록의 `location_name` (기본 `우리집`)

### config/.env

서버 접속 정보와 디바이스 등록 정보를 관리합니다. 이 파일은 `.gitignore`에 등록되어 git으로 관리되지 않으며, `config/.env.example`을 참고해 생성합니다.

```bash
SERVER_URL=https://example.com
REQUEST_TIMEOUT_SECONDS=10
api_key=
device_key=
```

- `SERVER_URL`: 서버 주소
- `api_key`, `device_key`: claim 등록에 성공하면 자동으로 기록됩니다. `run`/`dummy` 모드는 두 값이 모두 있어야 실행됩니다.

## 실행 모드

`--mode` 옵션으로 `test` / `dummy` / `run`을 지정합니다(기본 `run`).

| 모드 | 센서 측정 | 서버 전송 | 용도 |
| --- | --- | --- | --- |
| `test` | O | X (로그만) | 센서 정상 동작 확인 |
| `dummy` | X (고정값) | O | 서버 통신 확인 |
| `run` | O | O | 실제 운영 |

```bash
python3 src/climate_agent.py --mode test
python3 src/climate_agent.py --mode dummy
python3 src/climate_agent.py --mode run
```

- `test`: 1분마다 센서를 읽어 로그로만 출력합니다.
- `dummy`: 센서를 읽지 않고 `23.5C/50%`와 `24.0C/55%`를 1분마다 번갈아 전송하며, 로그에 `dummy value`로 표시합니다.
- `run`: 실제 센서 측정값을 전송합니다. `.env`에 `api_key`/`device_key`가 없으면 `디바이스가 등록되지 않았습니다.`를 출력하고 종료합니다.

## 디바이스 등록 (claim)

`--claim-code` 파라미터를 주면 첫 실행으로 간주하고 디바이스를 등록합니다.

```bash
python3 src/climate_agent.py --mode run --claim-code <claim_code>
```

- `POST {SERVER_URL}{server.claim_endpoint}`로 아래 본문을 전송합니다.

```json
{
  "claim_code": "<입력한 claim code>",
  "name": "TEMP_HUMIDITY",
  "type": "TEMP_HUMIDITY",
  "location_name": "우리집"
}
```

- `200`/`201` 응답이면 응답 본문의 `api_key`와 `device.device_key`를 `config/.env`에 저장(덮어쓰기)한 뒤 측정을 시작합니다.
- 그 외 응답이면 `디바이스 등록 실패` 메시지를 출력하고 종료합니다.

## 온습도 전송

```text
POST {SERVER_URL}/climate/{device_key}
Authorization: <api_key>

{
  "temperature_c": 24.5,   // 필수
  "humidity": 55.0          // 옵션
}
```

## 로그

- 파일명 형식: `edge.YYYYMMDD.HH.log` (예: `edge.20260503.09.log`)
- 각 줄에 일시, 로그 레벨, 내용을 기록합니다.
- 시간 단위로 파일이 바뀌고, `logging.retention_days`(기본 7일)를 초과한 로그는 자동 삭제됩니다.
- 컨테이너 로그는 호스트의 `log/` 디렉토리에 마운트되어 기록됩니다.

```bash
python3 src/climate_agent.py --help
```

## Docker 배포

라즈베리파이 배포는 `docker/` 디렉토리를 참고합니다. 자세한 내용은 [docker/README.md](docker/README.md)를 확인하세요.
