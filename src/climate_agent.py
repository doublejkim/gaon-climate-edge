from __future__ import annotations

import logging
import os
import re
import sys
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "config.yml"
DEFAULT_ENV_PATH = ROOT_DIR / "config" / ".env"
DEFAULT_LOG_DIR = ROOT_DIR / "log"
LOG_FILE_PREFIX = "edge"
DEFAULT_LOG_RETENTION_DAYS = 7

# dummy 모드에서 1분마다 번갈아 전송하는 고정 값입니다.
DUMMY_READINGS = (
    (23.5, 50.0),
    (24.0, 55.0),
)


@dataclass(frozen=True)
class SensorConfig:
    i2c_address: int


@dataclass(frozen=True)
class CollectionConfig:
    interval_seconds: int
    retry_limit: int
    retry_delay_seconds: int


@dataclass(frozen=True)
class ServerConfig:
    base_url: str | None
    climate_endpoint: str
    claim_endpoint: str
    api_key: str | None
    device_key: str | None
    timeout_seconds: float


@dataclass(frozen=True)
class DeviceConfig:
    type: str
    location_name: str


@dataclass(frozen=True)
class LoggingConfig:
    retention_days: int


@dataclass(frozen=True)
class AppConfig:
    sensor: SensorConfig
    collection: CollectionConfig
    server: ServerConfig
    device: DeviceConfig
    logging: LoggingConfig
    env_path: Path


@dataclass(frozen=True)
class ClimateReading:
    temperature_c: float
    humidity: float | None


class HourlyLogFileHandler(logging.Handler):
    def __init__(
        self,
        log_dir: Path = DEFAULT_LOG_DIR,
        retention_days: int = DEFAULT_LOG_RETENTION_DAYS,
    ) -> None:
        super().__init__()
        self._log_dir = log_dir
        self._retention_days = retention_days
        self._current_hour: str | None = None
        self._stream = None
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_old_logs(datetime.now())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            now = datetime.fromtimestamp(record.created)
            hour_key = now.strftime("%Y%m%d.%H")
            if hour_key != self._current_hour or self._stream is None:
                self._rotate(hour_key, now)

            message = self.format(record)
            self._stream.write(f"{message}\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._stream:
            self._stream.close()
            self._stream = None
        super().close()

    def _rotate(self, hour_key: str, now: datetime) -> None:
        if self._stream:
            self._stream.close()

        self._current_hour = hour_key
        log_path = self._log_dir / f"{LOG_FILE_PREFIX}.{hour_key}.log"
        self._stream = log_path.open("a", encoding="utf-8")
        self._cleanup_old_logs(now)

    def _cleanup_old_logs(self, now: datetime) -> None:
        cutoff = now - timedelta(days=self._retention_days)
        pattern = re.compile(rf"^{re.escape(LOG_FILE_PREFIX)}\.(\d{{8}})\.(\d{{2}})\.log$")

        for log_path in self._log_dir.glob(f"{LOG_FILE_PREFIX}.*.*.log"):
            match = pattern.match(log_path.name)
            if not match:
                continue

            try:
                log_hour = datetime.strptime("".join(match.groups()), "%Y%m%d%H")
            except ValueError:
                continue

            if log_hour < cutoff:
                log_path.unlink(missing_ok=True)


class Bme280Sensor:
    def __init__(self, config: SensorConfig) -> None:
        import board
        import busio
        from adafruit_bme280 import basic as adafruit_bme280

        i2c = busio.I2C(board.SCL, board.SDA)
        self._device = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=config.i2c_address)
        # forced mode: 매 측정마다 1회만 변환하고 슬립 상태로 돌아갑니다.
        # 1분 간격 같은 저빈도 수집에 적합합니다.
        self._device.mode = adafruit_bme280.MODE_FORCE

    def read(self) -> ClimateReading:
        temperature_c = self._device.temperature
        humidity = self._device.relative_humidity

        if temperature_c is None:
            raise RuntimeError("BME280 returned an empty temperature reading")

        return ClimateReading(
            temperature_c=float(temperature_c),
            humidity=float(humidity) if humidity is not None else None,
        )

    def close(self) -> None:
        pass


def parse_i2c_address(raw: Any) -> int:
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def load_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
    env_path: Path = DEFAULT_ENV_PATH,
) -> AppConfig:
    import yaml
    from dotenv import load_dotenv

    load_dotenv(env_path, override=True)

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    sensor = raw.get("sensor", {})
    collection = raw.get("collection", {})
    server = raw.get("server", {})
    logging_config = raw.get("logging", {})

    device_type = str(raw.get("type", "TEMP_HUMIDITY"))
    location_name = str(raw.get("device", {}).get("location_name", "우리집"))

    base_url = os.getenv("SERVER_URL", "").rstrip("/") or None

    return AppConfig(
        sensor=SensorConfig(
            i2c_address=parse_i2c_address(sensor.get("i2c_address", "0x76")),
        ),
        collection=CollectionConfig(
            interval_seconds=int(collection.get("interval_seconds", 60)),
            retry_limit=int(collection.get("retry_limit", 3)),
            retry_delay_seconds=int(collection.get("retry_delay_seconds", 2)),
        ),
        server=ServerConfig(
            base_url=base_url,
            climate_endpoint=str(server.get("climate_endpoint", "/climate/{device_key}")),
            claim_endpoint=str(server.get("claim_endpoint", "/devices/claim")),
            api_key=os.getenv("api_key") or None,
            device_key=os.getenv("device_key") or None,
            timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10")),
        ),
        device=DeviceConfig(
            type=device_type,
            location_name=location_name,
        ),
        logging=LoggingConfig(
            retention_days=max(1, int(logging_config.get("retention_days", DEFAULT_LOG_RETENTION_DAYS))),
        ),
        env_path=env_path,
    )


def build_climate_url(config: AppConfig, device_key: str) -> str:
    if not config.server.base_url:
        raise ValueError("SERVER_URL is required to build the climate URL")

    endpoint = config.server.climate_endpoint.format(device_key=device_key).lstrip("/")
    return f"{config.server.base_url}/{endpoint}"


def build_claim_url(config: AppConfig) -> str:
    if not config.server.base_url:
        raise ValueError("SERVER_URL is required to build the claim URL")

    endpoint = config.server.claim_endpoint.lstrip("/")
    return f"{config.server.base_url}/{endpoint}"


def update_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """기존 키는 덮어쓰고, 없는 키는 추가합니다."""
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)

    for key, value in updates.items():
        if key not in written:
            new_lines.append(f"{key}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def register_device(config: AppConfig, claim_code: str) -> tuple[str, str]:
    """claim code로 디바이스를 등록하고 (api_key, device_key)를 반환합니다."""
    import requests

    payload = {
        "claim_code": claim_code,
        "name": config.device.type,
        "type": config.device.type,
        "location_name": config.device.location_name,
    }
    claim_url = build_claim_url(config)
    logging.info("Requesting device claim at %s", claim_url)

    try:
        response = requests.post(
            claim_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=config.server.timeout_seconds,
        )
    except requests.RequestException as error:
        logging.error("디바이스 등록 실패: %s", error)
        raise SystemExit(1) from error

    if response.status_code not in (200, 201):
        logging.error(
            "디바이스 등록 실패 (HTTP %s): %s",
            response.status_code,
            response.text.strip(),
        )
        raise SystemExit(1)

    try:
        data = response.json()
    except ValueError as error:
        logging.error("디바이스 등록 실패: 응답이 JSON 형식이 아닙니다")
        raise SystemExit(1) from error

    api_key = data.get("api_key")
    device_key = (data.get("device") or {}).get("device_key")

    if not api_key or not device_key:
        logging.error("디바이스 등록 실패: 응답에 api_key 또는 device_key가 없습니다")
        raise SystemExit(1)

    update_env_file(config.env_path, {"api_key": str(api_key), "device_key": str(device_key)})
    logging.info("디바이스 등록 성공. api_key/device_key를 %s에 저장했습니다", config.env_path)
    return str(api_key), str(device_key)


def read_with_retry(sensor: Bme280Sensor, collection: CollectionConfig) -> ClimateReading:
    last_error: Exception | None = None

    for attempt in range(1, collection.retry_limit + 1):
        try:
            return sensor.read()
        except RuntimeError as error:
            last_error = error
            logging.warning(
                "Sensor read failed on attempt %s/%s: %s",
                attempt,
                collection.retry_limit,
                error,
            )
            time.sleep(collection.retry_delay_seconds)

    if last_error:
        raise last_error

    raise RuntimeError("Could not obtain a sensor reading")


def post_reading(config: AppConfig, api_key: str, device_key: str, reading: ClimateReading) -> None:
    import requests

    payload: dict[str, Any] = {"temperature_c": reading.temperature_c}
    if reading.humidity is not None:
        payload["humidity"] = reading.humidity

    response = requests.post(
        build_climate_url(config, device_key),
        json=payload,
        headers={"Content-Type": "application/json", "Authorization": api_key},
        timeout=config.server.timeout_seconds,
    )
    response.raise_for_status()


def parse_args() -> tuple[str, str | None]:
    parser = ArgumentParser(
        description="BME280 온습도 값을 수집해 서버로 전송하는 에지 프로그램입니다.",
    )
    parser.add_argument(
        "--mode",
        choices=("test", "dummy", "run"),
        default="run",
        help=(
            "실행 모드. test: 센서값을 로그로만 출력, "
            "dummy: 더미값을 서버로 전송, run: 실제 센서값을 서버로 전송."
        ),
    )
    parser.add_argument(
        "--claim-code",
        default=None,
        help="첫 실행 시 디바이스 등록에 사용할 claim code입니다.",
    )
    args = parser.parse_args()
    return args.mode, args.claim_code


def configure_logging(mode: str, logging_config: LoggingConfig) -> None:
    log_level = logging.DEBUG if mode == "test" else logging.INFO
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(formatter)

    file_handler = HourlyLogFileHandler(retention_days=logging_config.retention_days)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)


def ensure_registered(config: AppConfig) -> tuple[str, str]:
    """run/dummy 모드에서 api_key/device_key가 모두 있는지 확인합니다."""
    if not config.server.api_key or not config.server.device_key:
        logging.error("디바이스가 등록되지 않았습니다.")
        raise SystemExit(1)
    return config.server.api_key, config.server.device_key


def run() -> None:
    mode, claim_code = parse_args()
    config = load_config()
    configure_logging(mode, config.logging)
    logging.info("Climate agent started in %s mode", mode)

    # claim code가 전달되면 첫 실행으로 간주하고 디바이스를 등록합니다.
    if claim_code:
        api_key, device_key = register_device(config, claim_code)
        # .env가 갱신되었으므로 서버 설정을 다시 로드합니다.
        config = load_config()
    else:
        api_key = config.server.api_key
        device_key = config.server.device_key

    sensor: Bme280Sensor | None = None

    if mode in ("run", "dummy"):
        api_key, device_key = ensure_registered(config)

    if mode in ("test", "run"):
        sensor = Bme280Sensor(config.sensor)

    dummy_index = 0

    try:
        while True:
            try:
                if mode == "dummy":
                    temperature_c, humidity = DUMMY_READINGS[dummy_index % len(DUMMY_READINGS)]
                    dummy_index += 1
                    reading = ClimateReading(temperature_c=temperature_c, humidity=humidity)
                    logging.info(
                        "dummy value: %.1f C, %.1f%%",
                        reading.temperature_c,
                        reading.humidity,
                    )
                    post_reading(config, api_key, device_key, reading)
                    logging.info("Sent dummy value to %s", build_climate_url(config, device_key))
                else:
                    assert sensor is not None
                    reading = read_with_retry(sensor, config.collection)
                    logging.info(
                        "Collected climate reading: %.1f C, %s",
                        reading.temperature_c,
                        f"{reading.humidity:.1f}%" if reading.humidity is not None else "humidity n/a",
                    )

                    if mode == "test":
                        logging.info("test mode: skipped sending to server")
                    else:
                        post_reading(config, api_key, device_key, reading)
                        logging.info("Sent reading to %s", build_climate_url(config, device_key))
            except Exception:
                logging.exception("Climate collection cycle failed")

            time.sleep(config.collection.interval_seconds)
    finally:
        if sensor is not None:
            sensor.close()


if __name__ == "__main__":
    run()
