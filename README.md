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
- `device.id`: 서버에 함께 전달할 장비 식별자

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

전송 URL은 아래처럼 만들어집니다.

```text
{CLIMATE_SERVER_URL}/climate/{device_id}
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
  "device_id": "gaon-climate-edge-01",
  "temperature_c": 24.5,
  "humidity": 55.0,
  "measured_at": "2026-05-03T04:00:00+00:00"
}
```

## 도움말

실행 옵션은 아래 명령으로 확인할 수 있습니다.

```bash
python3 src/climate_agent.py --help
```
