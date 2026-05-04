from __future__ import annotations

import logging
import os
import re
import sys
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "config.yml"
DEFAULT_ENV_PATH = ROOT_DIR / "config" / ".env"
DEFAULT_LOG_DIR = ROOT_DIR / "log"
LOG_FILE_PREFIX = "gaon-climate-edge"
DEFAULT_LOG_RETENTION_DAYS = 3


@dataclass(frozen=True)
class SensorConfig:
    board_pin: str
    use_pulseio: bool


@dataclass(frozen=True)
class CollectionConfig:
    interval_seconds: int
    max_temperature_delta_c: float
    retry_limit: int
    retry_delay_seconds: int


@dataclass(frozen=True)
class ServerConfig:
    base_url: str | None
    endpoint: str
    api_key: str | None
    timeout_seconds: float


@dataclass(frozen=True)
class LoggingConfig:
    retention_days: int


@dataclass(frozen=True)
class AppConfig:
    sensor: SensorConfig
    collection: CollectionConfig
    server: ServerConfig
    logging: LoggingConfig
    device_key: str


@dataclass(frozen=True)
class ClimateReading:
    temperature_c: float
    humidity: float
    measured_at: str


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
            if hour_key != self._current_hour:
                self._rotate(hour_key, now)

            message = self.format(record)
            if self._stream is None:
                self._rotate(hour_key, now)
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


class DhtSensor:
    def __init__(self, config: SensorConfig) -> None:
        import adafruit_dht
        import board

        pin = getattr(board, config.board_pin)
        self._device = adafruit_dht.DHT22(pin, use_pulseio=config.use_pulseio)

    def read(self) -> ClimateReading:
        temperature_c = self._device.temperature
        humidity = self._device.humidity

        if temperature_c is None or humidity is None:
            raise RuntimeError("DHT22 returned an empty reading")

        return ClimateReading(
            temperature_c=float(temperature_c),
            humidity=float(humidity),
            measured_at=datetime.now(timezone.utc).isoformat(),
        )

    def close(self) -> None:
        self._device.exit()


def load_config(
    mode: str,
    config_path: Path = DEFAULT_CONFIG_PATH,
    env_path: Path = DEFAULT_ENV_PATH,
) -> AppConfig:
    import yaml
    from dotenv import load_dotenv

    load_dotenv(env_path)

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    sensor = raw.get("sensor", {})
    collection = raw.get("collection", {})
    server = raw.get("server", {})
    logging_config = raw.get("logging", {})
    device = raw.get("device", {})

    base_url = os.getenv("CLIMATE_SERVER_URL", "").rstrip("/") or None
    if mode == "prod" and not base_url:
        raise ValueError("CLIMATE_SERVER_URL is required in config/.env")

    return AppConfig(
        sensor=SensorConfig(
            board_pin=str(sensor.get("board_pin", "D4")),
            use_pulseio=bool(sensor.get("use_pulseio", False)),
        ),
        collection=CollectionConfig(
            interval_seconds=int(collection.get("interval_seconds", 60)),
            max_temperature_delta_c=float(collection.get("max_temperature_delta_c", 5.0)),
            retry_limit=int(collection.get("retry_limit", 3)),
            retry_delay_seconds=int(collection.get("retry_delay_seconds", 2)),
        ),
        server=ServerConfig(
            base_url=base_url,
            endpoint=str(server.get("endpoint", "/clidmate/{device_key}")),
            api_key=os.getenv("CLIMATE_API_KEY") or None,
            timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10")),
        ),
        logging=LoggingConfig(
            retention_days=max(1, int(logging_config.get("retention_days", DEFAULT_LOG_RETENTION_DAYS))),
        ),
        device_key=str(device.get("key", device.get("id", "gaon-climate-edge-01"))),
    )


def build_url(config: AppConfig) -> str:
    if not config.server.base_url:
        raise ValueError("CLIMATE_SERVER_URL is required to build the server URL")

    endpoint = config.server.endpoint.format(device_key=config.device_key, device_id=config.device_key).lstrip("/")
    return f"{config.server.base_url}/{endpoint}"


def read_with_validation(
    sensor: DhtSensor,
    previous_reading: ClimateReading | None,
    collection: CollectionConfig,
) -> ClimateReading:
    last_error: Exception | None = None

    for attempt in range(1, collection.retry_limit + 1):
        try:
            reading = sensor.read()
        except RuntimeError as error:
            last_error = error
            logging.warning("Sensor read failed on attempt %s/%s: %s", attempt, collection.retry_limit, error)
            time.sleep(collection.retry_delay_seconds)
            continue

        if previous_reading is None:
            return reading

        delta = abs(reading.temperature_c - previous_reading.temperature_c)
        if delta <= collection.max_temperature_delta_c:
            return reading

        logging.warning(
            "Temperature delta %.2f C exceeded threshold %.2f C on attempt %s/%s",
            delta,
            collection.max_temperature_delta_c,
            attempt,
            collection.retry_limit,
        )
        time.sleep(collection.retry_delay_seconds)

    if last_error:
        raise last_error

    raise RuntimeError("Could not obtain a stable temperature reading")


def post_reading(config: AppConfig, reading: ClimateReading) -> None:
    import requests

    payload: dict[str, Any] = {
        "temperature_c": reading.temperature_c,
        "humidity": reading.humidity,
        "measured_at": reading.measured_at,
    }
    headers = {"Content-Type": "application/json"}

    if config.server.api_key:
        headers["Authorization"] = f"Bearer {config.server.api_key}"

    response = requests.post(
        build_url(config),
        json=payload,
        headers=headers,
        timeout=config.server.timeout_seconds,
    )
    response.raise_for_status()


def parse_args() -> str:
    parser = ArgumentParser(description="Collect DHT22 climate data and optionally send it to the server.")
    parser.add_argument(
        "--mode",
        choices=("local", "prod"),
        default="local",
        help="Execution mode. local logs readings only; prod sends readings to the configured server.",
    )
    return parser.parse_args().mode


def configure_logging(mode: str, logging_config: LoggingConfig) -> None:
    log_level = logging.DEBUG if mode == "local" else logging.INFO
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


def handle_reading(mode: str, config: AppConfig, reading: ClimateReading) -> None:
    logging.info(
        "Collected climate reading: %.1f C, %.1f%% at %s",
        reading.temperature_c,
        reading.humidity,
        reading.measured_at,
    )

    if mode == "local":
        logging.info("Local mode: skipped POST to %s", config.server.endpoint)
        return

    post_reading(config, reading)
    logging.info("Prod mode: posted climate reading to %s", build_url(config))


def run() -> None:
    mode = parse_args()
    config = load_config(mode)
    configure_logging(mode, config.logging)
    sensor = DhtSensor(config.sensor)
    previous_reading: ClimateReading | None = None
    logging.info("Climate agent started in %s mode", mode)

    try:
        while True:
            try:
                reading = read_with_validation(sensor, previous_reading, config.collection)
                handle_reading(mode, config, reading)
                previous_reading = reading
            except Exception:
                logging.exception("Climate collection cycle failed")

            time.sleep(config.collection.interval_seconds)
    finally:
        sensor.close()


if __name__ == "__main__":
    run()
