from __future__ import annotations

import logging
import os
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "config.yml"
DEFAULT_ENV_PATH = ROOT_DIR / "config" / ".env"


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
class AppConfig:
    sensor: SensorConfig
    collection: CollectionConfig
    server: ServerConfig
    device_id: str


@dataclass(frozen=True)
class ClimateReading:
    temperature_c: float
    humidity: float
    measured_at: str


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
            endpoint=str(server.get("endpoint", "/climate/{device_id}")),
            api_key=os.getenv("CLIMATE_API_KEY") or None,
            timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10")),
        ),
        device_id=str(device.get("id", "gaon-climate-edge-01")),
    )


def build_url(config: AppConfig) -> str:
    if not config.server.base_url:
        raise ValueError("CLIMATE_SERVER_URL is required to build the server URL")

    endpoint = config.server.endpoint.format(device_id=config.device_id).lstrip("/")
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
        "device_id": config.device_id,
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    mode = parse_args()
    config = load_config(mode)
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
