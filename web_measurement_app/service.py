from __future__ import annotations

import asyncio
import csv
import datetime as dt
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, TextIO, Tuple

import subprocess

from pydantic import BaseModel, Field, validator

from .logger_core import (
    ADVANCED_EVENT_BSSID_CHANGED,
    ADVANCED_EVENT_PING_TIMEOUT,
    ADVANCED_EVENT_SSH_FAILED,
    CHANNEL_FILTER,
    DEFAULT_BAND,
    DEFAULT_INTERVAL,
    DEFAULT_LOG_BASE,
    DEFAULT_MEASUREMENT_MODE,
    DEFAULT_PING_FAIL_VALUE,
    DEFAULT_PING_TARGET,
    DEFAULT_PING_TIMEOUT_MS,
    DEFAULT_REMOTE_NEIGHBOR_EVERY,
    DEFAULT_REMOTE_PORT,
    DEFAULT_REMOTE_USER,
    DEFAULT_SSID,
    DEFAULT_TIMEZONE,
    DEFAULT_USE_GATEWAY,
    DEFAULT_USE_SUDO,
    DEFAULT_WIFI_DISCONNECTED_VALUE,
    HEADERS,
    NEIGHBOR_HEADERS,
    apply_neighbor_summary,
    collect_remote_advanced_snapshot,
    ensure_remote_ssh_key,
    fetch_remote_wifi_state,
    fetch_wifi_rows,
    get_ping_result,
    prepare_neighbor_log_file,
    prepare_log_file,
    prepare_sidecar_file,
    probe_remote_ssh,
    remove_remote_ssh_key,
    resolve_ping_target,
    scan_local_neighbors,
    should_run_neighbor_scan,
)


class MeasurementConfig(BaseModel):
    measurement_mode: str = Field(default=DEFAULT_MEASUREMENT_MODE)
    ssid: str = Field(default=DEFAULT_SSID)
    band: str = Field(default=DEFAULT_BAND)
    channel_min: Optional[int] = None
    channel_max: Optional[int] = None
    auto_gateway: bool = Field(default=DEFAULT_USE_GATEWAY)
    ping_target: Optional[str] = None
    interval: float = Field(default=DEFAULT_INTERVAL, gt=0)
    ping_fail_value: float = Field(default=DEFAULT_PING_FAIL_VALUE)
    ping_timeout_ms: int = Field(default=DEFAULT_PING_TIMEOUT_MS, ge=1, le=60000)
    timeout_as_numeric: bool = Field(default=True)
    wifi_disconnected_value: float = Field(default=DEFAULT_WIFI_DISCONNECTED_VALUE)
    prefix: Optional[str] = None
    log_base: str = Field(default=DEFAULT_LOG_BASE)
    output_dir: str = Field(default=".")
    use_sudo: bool = Field(default=DEFAULT_USE_SUDO)
    sync_time: bool = Field(default=False)
    timezone: str = Field(default=DEFAULT_TIMEZONE)
    retain_rows: int = Field(default=20000, ge=1000, le=200000)
    remote_host: Optional[str] = None
    remote_user: str = Field(default=DEFAULT_REMOTE_USER)
    remote_port: int = Field(default=DEFAULT_REMOTE_PORT, ge=1, le=65535)
    remote_identity_file: Optional[str] = None
    remote_enable_neighbor_scan: bool = Field(default=True)
    remote_setup_ssh_key: bool = Field(default=True)
    remote_cleanup_ssh_key: bool = Field(default=True)
    remote_delete_local_key: bool = Field(default=True)
    remote_ssh_key_comment: Optional[str] = None
    remote_neighbor_every: int = Field(default=DEFAULT_REMOTE_NEIGHBOR_EVERY, ge=0, le=3600)
    remote_neighbor_ssid: Optional[str] = None
    remote_advanced_enabled: bool = Field(default=False)
    remote_advanced_include_neighbor: bool = Field(default=False)
    remote_advanced_include_routes: bool = Field(default=False)
    remote_advanced_include_ip_addr: bool = Field(default=False)
    remote_advanced_include_wifi_details: bool = Field(default=False)
    remote_advanced_include_journal: bool = Field(default=False)
    remote_advanced_snapshot_on_bssid_change: bool = Field(default=False)
    remote_advanced_snapshot_on_ping_timeout: bool = Field(default=False)
    remote_advanced_ping_timeout_streak: int = Field(default=1, ge=1, le=20)
    remote_advanced_max_output_chars: int = Field(default=12000, ge=200, le=200000)

    @validator(
        "ssid",
        "band",
        "ping_target",
        "prefix",
        "log_base",
        "output_dir",
        "timezone",
        "remote_host",
        "remote_user",
        "remote_identity_file",
        "remote_ssh_key_comment",
        "remote_neighbor_ssid",
        pre=True,
    )
    def normalize_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @validator("measurement_mode")
    def validate_measurement_mode(cls, value: str) -> str:
        if value not in {"local", "remote_ssh"}:
            raise ValueError("measurement_mode must be local or remote_ssh")
        return value

    @validator("band")
    def validate_band(cls, value: str) -> str:
        if value not in CHANNEL_FILTER:
            raise ValueError(f"band must be one of {list(CHANNEL_FILTER)}")
        return value

    @validator("channel_min", always=True)
    def set_channel_min(cls, value: Optional[int], values: Dict[str, Any]) -> int:
        if value is not None:
            return value
        band = values.get("band", DEFAULT_BAND)
        return CHANNEL_FILTER[band]["min"]

    @validator("channel_max", always=True)
    def set_channel_max(cls, value: Optional[int], values: Dict[str, Any]) -> int:
        if value is not None:
            return value
        band = values.get("band", DEFAULT_BAND)
        return CHANNEL_FILTER[band]["max"]

    @validator("channel_max")
    def ensure_channel_order(cls, channel_max: int, values: Dict[str, Any]) -> int:
        channel_min = values.get("channel_min")
        if channel_min is not None and channel_max < channel_min:
            raise ValueError("channel_max must be >= channel_min")
        return channel_max

    @validator("remote_host", always=True)
    def validate_remote_host(cls, value: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        if values.get("measurement_mode") == "remote_ssh" and not (value or "").strip():
            raise ValueError("remote_host is required when measurement_mode=remote_ssh")
        return value


class MeasurementStatus(BaseModel):
    running: bool
    current_point: int
    log_index: int
    log_file: Optional[str]
    neighbor_log_file: Optional[str]
    advanced_log_file: Optional[str]
    ping_target: Optional[str]
    ping_target_source: Optional[str]
    config: Optional[MeasurementConfig]
    last_error: Optional[str]
    started_at: Optional[str]


def synchronize_time(target_timezone: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property", "Timezone", "--value"],
            capture_output=True,
            text=True,
            check=True,
        )
        original_timezone = result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    for cmd in (
        ["sudo", "systemctl", "start", "systemd-timesyncd"],
        ["sudo", "systemctl", "enable", "systemd-timesyncd"],
    ):
        try:
            subprocess.run(cmd, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            break

    if not target_timezone or target_timezone == original_timezone:
        return original_timezone

    try:
        subprocess.run(["sudo", "timedatectl", "set-timezone", target_timezone], check=True)
        return original_timezone
    except (FileNotFoundError, subprocess.CalledProcessError):
        return original_timezone


def restore_timezone(timezone_name: Optional[str]) -> None:
    if not timezone_name:
        return
    try:
        subprocess.run(["sudo", "timedatectl", "set-timezone", timezone_name], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass


class MeasurementService:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._current_point = 1
        self._log_index = 0
        self._listeners: set[asyncio.Queue] = set()
        self._history: Dict[int, Deque[Dict[str, Any]]] = defaultdict(deque)
        self._config: Optional[MeasurementConfig] = None
        self._log_path: Optional[Path] = None
        self._neighbor_log_path: Optional[Path] = None
        self._neighbor_log_index = 0
        self._neighbor_scan_index = 0
        self._advanced_log_path: Optional[Path] = None
        self._ping_target_info: Optional[Tuple[str, str]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_error: Optional[str] = None
        self._started_at: Optional[dt.datetime] = None
        self._original_timezone: Optional[str] = None
        self._last_seen_remote_bssid: Optional[str] = None
        self._remote_ping_timeout_streak = 0
        self._remote_timeout_snapshot_taken = False

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self, config: MeasurementConfig) -> MeasurementStatus:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Measurement is already running")
            self._config = config
            self._stop_event.clear()
            self._current_point = 1
            self._log_index = 0
            self._history.clear()
            self._last_error = None
            self._started_at = dt.datetime.now(dt.timezone.utc)
            prefix = config.prefix or ""
            self._log_path = prepare_log_file(prefix, config.log_base, config.output_dir)
            self._neighbor_log_path = prepare_neighbor_log_file(self._log_path)
            self._neighbor_log_index = 0
            self._neighbor_scan_index = 0
            self._advanced_log_path = (
                prepare_sidecar_file(prefix, f"{config.log_base}_remote_advanced", config.output_dir, ".jsonl")
                if config.measurement_mode == "remote_ssh" and config.remote_advanced_enabled
                else None
            )
            self._last_seen_remote_bssid = None
            self._remote_ping_timeout_streak = 0
            self._remote_timeout_snapshot_taken = False

            if config.measurement_mode == "remote_ssh":
                self._ping_target_info = (
                    (config.ping_target, "manual")
                    if config.ping_target
                    else (None, "remote_gateway_auto")
                )
                try:
                    probe_remote_ssh(
                        host=config.remote_host or "",
                        user=config.remote_user,
                        port=config.remote_port,
                        identity_file=config.remote_identity_file,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        "SSH接続確認に失敗しました。先に「SSH準備」を実行してから開始してください。"
                    ) from exc
            else:
                self._ping_target_info = resolve_ping_target(
                    config.ping_target, config.auto_gateway, DEFAULT_PING_TARGET
                )

            self._original_timezone = synchronize_time(config.timezone) if config.sync_time else None
            self._thread = threading.Thread(target=self._run_loop, name="wifi-logger", daemon=True)
            self._thread.start()
        return self.status()

    def stop(self) -> MeasurementStatus:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            config = self._config
        if thread and thread.is_alive():
            thread.join(timeout=5)
        restore_timezone(self._original_timezone)
        if config and config.measurement_mode == "remote_ssh" and config.remote_cleanup_ssh_key:
            try:
                remove_remote_ssh_key(
                    host=config.remote_host or "",
                    user=config.remote_user,
                    port=config.remote_port,
                    identity_file=config.remote_identity_file,
                    delete_local=config.remote_delete_local_key,
                )
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
        return self.status()

    def status(self) -> MeasurementStatus:
        running = self._thread is not None and self._thread.is_alive()
        started_at_str = self._started_at.isoformat() if self._started_at else None
        return MeasurementStatus(
            running=running,
            current_point=self._current_point,
            log_index=self._log_index,
            log_file=str(self._log_path) if self._log_path else None,
            neighbor_log_file=str(self._neighbor_log_path) if self._neighbor_log_path else None,
            advanced_log_file=str(self._advanced_log_path) if self._advanced_log_path else None,
            ping_target=self._ping_target_info[0] if self._ping_target_info else None,
            ping_target_source=self._ping_target_info[1] if self._ping_target_info else None,
            config=self._config,
            last_error=self._last_error,
            started_at=started_at_str,
        )

    def advance_point(self) -> Dict[str, int]:
        with self._lock:
            if not (self._thread and self._thread.is_alive()):
                raise RuntimeError("Measurement is not running")
            completed_point = self._current_point
            self._current_point += 1
        return {"completed_point": completed_point, "current_point": self._current_point}

    def revert_point(self) -> Dict[str, int]:
        with self._lock:
            if not (self._thread and self._thread.is_alive()):
                raise RuntimeError("Measurement is not running")
            if self._current_point <= 1:
                raise RuntimeError("Current point cannot be decreased further")
            self._current_point -= 1
            current_point = self._current_point
        return {"current_point": current_point}

    def get_logs(self, point: int) -> List[Dict[str, Any]]:
        with self._lock:
            deque_list = self._history.get(point, deque())
            return list(deque_list)

    def register_listener(self) -> asyncio.Queue:
        if not self._loop:
            raise RuntimeError("Event loop not bound")
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._listeners.add(queue)
        return queue

    def unregister_listener(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._listeners.discard(queue)

    def _run_loop(self) -> None:
        assert self._config and self._log_path and self._neighbor_log_path and self._ping_target_info
        config = self._config
        target_ip, _target_source = self._ping_target_info
        sample_no = 0

        try:
            with (
                open(self._log_path, "w", newline="", encoding="utf-8-sig") as csv_file,
                open(self._neighbor_log_path, "w", newline="", encoding="utf-8-sig") as neighbor_file,
            ):
                writer = csv.writer(csv_file)
                writer.writerow(HEADERS)
                neighbor_writer = csv.writer(neighbor_file)
                neighbor_writer.writerow(NEIGHBOR_HEADERS)
                advanced_file: Optional[TextIO] = None
                try:
                    if self._advanced_log_path:
                        advanced_file = open(self._advanced_log_path, "w", encoding="utf-8")

                    while not self._stop_event.is_set():
                        sample_no += 1
                        if config.measurement_mode == "remote_ssh":
                            record = self._run_remote_iteration(
                                writer, csv_file, neighbor_writer, config, sample_no
                            )
                            if record and advanced_file and config.remote_advanced_enabled:
                                self._maybe_capture_remote_advanced_snapshot(
                                    advanced_file=advanced_file,
                                    record=record,
                                    config=config,
                                )
                        else:
                            self._run_local_iteration(
                                writer, csv_file, neighbor_writer, config, target_ip, sample_no
                            )
                        time.sleep(config.interval)
                finally:
                    if advanced_file is not None:
                        advanced_file.close()
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
        finally:
            self._stop_event.set()

    def _run_remote_iteration(
        self,
        writer: csv.writer,
        csv_file,
        neighbor_writer: csv.writer,
        config: MeasurementConfig,
        sample_no: int,
    ) -> Dict[str, Any]:
        try:
            remote_row = fetch_remote_wifi_state(
                host=config.remote_host or "",
                user=config.remote_user,
                port=config.remote_port,
                identity_file=config.remote_identity_file,
                ping_target=config.ping_target,
                neighbor_every=config.remote_neighbor_every if config.remote_enable_neighbor_scan else 0,
                sample_index=sample_no,
                neighbor_ssid=config.remote_neighbor_ssid,
            )
            error_message = ""
            wifi_rows = [remote_row]
        except Exception as exc:  # noqa: BLE001
            wifi_rows = []
            error_message = str(exc)

        date_str, time_str, point_value = self._timestamp_and_point()

        if wifi_rows:
            row = wifi_rows[0]
            neighbor_rows = list(row.pop("_neighbor_rows", []))
            if row.get("neighbor_scan_ran") == "yes":
                self._write_neighbor_rows(
                    neighbor_writer,
                    neighbor_rows,
                    point_value,
                    date_str,
                    time_str,
                    str(row.get("host", "")),
                )
            if row.get("ping_target"):
                target_source = "manual" if config.ping_target else "remote_gateway"
                self._ping_target_info = (str(row["ping_target"]), target_source)
            ping_target_value = (
                str(row.get("ping_target") or "")
                or (self._ping_target_info[0] if self._ping_target_info and self._ping_target_info[0] else "")
            )
            ping_target_source = self._ping_target_info[1] if self._ping_target_info else ""
            ping_status = str(row.get("ping_status", "") or "")
            ping_ms = row.get("ping_ms", "")
            arp_target_state = str(row.get("arp_target_state", "") or "")
            if ping_status == "timeout" and ping_ms in {"", None}:
                ping_ms = (
                    str(config.ping_fail_value)
                    if config.timeout_as_numeric
                    else "NaN"
                )
            log_line = [
                self._log_index,
                point_value,
                date_str,
                time_str,
                row.get("ssid", ""),
                row.get("bssid", ""),
                row.get("channel", ""),
                row.get("rate", ""),
                row.get("signal", ""),
                row.get("dbm", ""),
                "",
                "",
                ping_ms,
                ping_status,
                row.get("neighbor_scan_ran", ""),
                row.get("neighbor_match_ssid", ""),
                row.get("neighbor_count_visible", ""),
                row.get("neighbor_count_same_ssid", ""),
                row.get("neighbor_bssid_list", ""),
                row.get("best_neighbor_ssid", ""),
                row.get("best_neighbor_bssid", ""),
                row.get("best_neighbor_channel", ""),
                row.get("best_neighbor_rate", ""),
                row.get("best_neighbor_signal", ""),
                row.get("best_neighbor_dbm", ""),
                row.get("best_neighbor_signal_gap", ""),
                arp_target_state,
                ping_target_value,
                ping_target_source,
                row.get("host", ""),
                row.get("ssh_status", ""),
                row.get("error", ""),
            ]
            message = str(row.get("error", "") or error_message)
        else:
            log_line = [
                self._log_index,
                point_value,
                date_str,
                time_str,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                str(config.wifi_disconnected_value) if config.timeout_as_numeric else "NaN",
                "ssh_failed",
                "no",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                self._ping_target_info[0] if self._ping_target_info and self._ping_target_info[0] else "",
                self._ping_target_info[1] if self._ping_target_info else "",
                config.remote_host or "",
                "error",
                error_message or "remote_capture_failed",
            ]
            message = error_message or "remote_capture_failed"

        return self._write_and_publish_record(writer, csv_file, log_line, message, config.retain_rows)

    def _run_local_iteration(
        self,
        writer: csv.writer,
        csv_file,
        neighbor_writer: csv.writer,
        config: MeasurementConfig,
        target_ip: str,
        sample_no: int,
    ) -> None:
        try:
            wifi_rows = fetch_wifi_rows(
                config.use_sudo,
                config.ssid,
                config.channel_min,
                config.channel_max,
            )
            error_message = ""
        except RuntimeError as exc:
            wifi_rows = []
            error_message = str(exc)

        date_str, time_str, point_value = self._timestamp_and_point()

        if config.remote_enable_neighbor_scan and should_run_neighbor_scan(sample_no, config.remote_neighbor_every):
            try:
                neighbor_rows = scan_local_neighbors(config.use_sudo, config.remote_neighbor_ssid)
                for row in wifi_rows:
                    apply_neighbor_summary(row, neighbor_rows, config.remote_neighbor_ssid)
                self._write_neighbor_rows(
                    neighbor_writer,
                    neighbor_rows,
                    point_value,
                    date_str,
                    time_str,
                    "local",
                )
            except RuntimeError as exc:
                error_message = error_message or str(exc)

        if wifi_rows:
            for row in wifi_rows:
                icmp_seq, ttl, time_ms, ping_status = get_ping_result(
                    target_ip,
                    config.timeout_as_numeric,
                    config.ping_fail_value,
                    config.ping_timeout_ms,
                )
                log_line = [
                    self._log_index,
                    point_value,
                    date_str,
                    time_str,
                    row["ssid"],
                    row.get("bssid", ""),
                    row["channel"],
                    row["rate"],
                    row["signal"],
                    self._format_dbm(row.get("dbm", "")),
                    icmp_seq,
                    ttl,
                    time_ms,
                    ping_status,
                    row.get("neighbor_scan_ran", "no"),
                    row.get("neighbor_match_ssid", ""),
                    row.get("neighbor_count_visible", ""),
                    row.get("neighbor_count_same_ssid", ""),
                    row.get("neighbor_bssid_list", ""),
                    row.get("best_neighbor_ssid", ""),
                    row.get("best_neighbor_bssid", ""),
                    row.get("best_neighbor_channel", ""),
                    row.get("best_neighbor_rate", ""),
                    row.get("best_neighbor_signal", ""),
                    row.get("best_neighbor_dbm", ""),
                    row.get("best_neighbor_signal_gap", ""),
                    "",
                    target_ip,
                    self._ping_target_info[1] if self._ping_target_info else "",
                    "local",
                    "",
                    "",
                ]
                self._write_and_publish_record(writer, csv_file, log_line, error_message, config.retain_rows)
        else:
            icmp_seq, ttl, time_ms, _ping_status = get_ping_result(
                target_ip,
                config.timeout_as_numeric,
                config.ping_fail_value,
                config.ping_timeout_ms,
            )
            placeholder_time = str(config.wifi_disconnected_value) if config.timeout_as_numeric else "NaN"
            log_line = [
                self._log_index,
                point_value,
                date_str,
                time_str,
                "",
                "",
                "",
                "",
                "",
                "",
                icmp_seq,
                ttl,
                placeholder_time,
                "wifi_disconnected",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                target_ip,
                self._ping_target_info[1] if self._ping_target_info else "",
                "local",
                "",
                error_message or "wifi_disconnected",
            ]
            self._write_and_publish_record(
                writer,
                csv_file,
                log_line,
                error_message or "Wi-Fi disconnected placeholder recorded",
                config.retain_rows,
            )

    @staticmethod
    def _format_dbm(value: Any) -> str:
        if isinstance(value, (int, float)):
            return f"{value:.1f}"
        return str(value or "")

    def _write_neighbor_rows(
        self,
        writer: csv.writer,
        neighbors: List[Dict[str, str]],
        point: int,
        date_str: str,
        time_str: str,
        host: str,
    ) -> None:
        self._neighbor_scan_index += 1
        scan_index = self._neighbor_scan_index
        for neighbor in neighbors:
            signal = neighbor.get("signal", "")
            try:
                dbm = f"{(int(signal) / 2) - 100:.1f}"
            except (TypeError, ValueError):
                dbm = ""
            writer.writerow(
                [
                    self._neighbor_log_index,
                    point,
                    date_str,
                    time_str,
                    host,
                    scan_index,
                    neighbor.get("ssid", ""),
                    neighbor.get("bssid", ""),
                    neighbor.get("channel", ""),
                    neighbor.get("rate", ""),
                    signal,
                    dbm,
                ]
            )
            self._neighbor_log_index += 1

    def _timestamp_and_point(self) -> Tuple[str, str, int]:
        now = dt.datetime.now(dt.timezone.utc).astimezone()
        date_str = now.strftime("%Y-%m-%d")
        time_str = f'="{now.strftime("%H:%M:%S.%f")[:12]}"'
        with self._lock:
            point_value = self._current_point
        return date_str, time_str, point_value

    def _write_and_publish_record(
        self,
        writer: csv.writer,
        csv_file,
        log_line: List[Any],
        message: str,
        retain_rows: int,
    ) -> Dict[str, Any]:
        writer.writerow(log_line)
        csv_file.flush()
        self._log_index += 1
        record = self._build_record(log_line, message)
        self._append_history(int(log_line[1]), record, retain_rows)
        self._publish(record)
        return record

    def _maybe_capture_remote_advanced_snapshot(
        self,
        *,
        advanced_file: TextIO,
        record: Dict[str, Any],
        config: MeasurementConfig,
    ) -> None:
        reasons: List[str] = []
        bssid = str(record.get("bssid", "") or "").strip()
        status = str(record.get("status", "") or "")
        ssh_status = str(record.get("ssh_status", "") or "")

        if config.remote_advanced_snapshot_on_bssid_change and bssid:
            if self._last_seen_remote_bssid and bssid != self._last_seen_remote_bssid:
                reasons.append(ADVANCED_EVENT_BSSID_CHANGED)
            self._last_seen_remote_bssid = bssid
        elif bssid:
            self._last_seen_remote_bssid = bssid

        timeout_like = status in {"ping_timeout", "timeout", "ssh_failed"}
        if timeout_like:
            self._remote_ping_timeout_streak += 1
        else:
            self._remote_ping_timeout_streak = 0
            self._remote_timeout_snapshot_taken = False

        if ssh_status and ssh_status != "ok":
            reasons.append(ADVANCED_EVENT_SSH_FAILED)

        if (
            config.remote_advanced_snapshot_on_ping_timeout
            and self._remote_ping_timeout_streak >= config.remote_advanced_ping_timeout_streak
            and not self._remote_timeout_snapshot_taken
        ):
            reasons.append(ADVANCED_EVENT_PING_TIMEOUT)
            self._remote_timeout_snapshot_taken = True

        if not reasons:
            return

        if ssh_status and ssh_status != "ok":
            snapshot = {
                "skipped": {
                    "reason": "ssh_unavailable",
                    "ssh_status": ssh_status,
                }
            }
        else:
            snapshot = collect_remote_advanced_snapshot(
                host=config.remote_host or "",
                user=config.remote_user,
                port=config.remote_port,
                identity_file=config.remote_identity_file,
                include_neighbor=config.remote_advanced_include_neighbor,
                include_routes=config.remote_advanced_include_routes,
                include_ip_addr=config.remote_advanced_include_ip_addr,
                include_wifi_details=config.remote_advanced_include_wifi_details,
                include_journal=config.remote_advanced_include_journal,
                max_output_chars=config.remote_advanced_max_output_chars,
            )
        record["advanced_snapshot_reasons"] = reasons
        event = {
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "point": record.get("point"),
            "index": record.get("index"),
            "host": record.get("host"),
            "ssid": record.get("ssid"),
            "bssid": record.get("bssid"),
            "channel": record.get("channel"),
            "signal_strength": record.get("signal_strength"),
            "rssi_dbm": record.get("rssi_dbm"),
            "ping_ms": record.get("ping_ms"),
            "status": status,
            "ssh_status": ssh_status,
            "reasons": reasons,
            "snapshot": snapshot,
        }
        advanced_file.write(json.dumps(event, ensure_ascii=False) + "\n")
        advanced_file.flush()

    def _build_record(self, log_line: List[Any], message: str) -> Dict[str, Any]:
        record = {
            "index": log_line[0],
            "point": log_line[1],
            "date": log_line[2],
            "time": log_line[3],
            "ssid": log_line[4],
            "bssid": log_line[5],
            "channel": log_line[6],
            "rate": log_line[7],
            "signal_strength": log_line[8],
            "rssi_dbm": log_line[9],
            "icmp_seq": log_line[10],
            "ttl": log_line[11],
            "ping_ms": log_line[12],
            "status": log_line[13],
            "neighbor_scan_ran": log_line[14],
            "neighbor_match_ssid": log_line[15],
            "neighbor_count_visible": log_line[16],
            "neighbor_count_same_ssid": log_line[17],
            "neighbor_bssid_list": log_line[18],
            "best_neighbor_ssid": log_line[19],
            "best_neighbor_bssid": log_line[20],
            "best_neighbor_channel": log_line[21],
            "best_neighbor_rate": log_line[22],
            "best_neighbor_signal": log_line[23],
            "best_neighbor_dbm": log_line[24],
            "best_neighbor_signal_gap": log_line[25],
            "arp_target_state": log_line[26],
            "ping_target": log_line[27],
            "ping_target_source": log_line[28],
            "host": log_line[29],
            "ssh_status": log_line[30],
            "error": log_line[31],
        }
        if message:
            record["message"] = message
        return record

    def _append_history(self, point: int, record: Dict[str, Any], retain_rows: int) -> None:
        with self._lock:
            bucket = self._history[point]
            bucket.append(record)
            while len(bucket) > retain_rows:
                bucket.popleft()

    def _publish(self, record: Dict[str, Any]) -> None:
        if not self._loop:
            return
        with self._lock:
            listeners = list(self._listeners)
        for queue in listeners:
            asyncio.run_coroutine_threadsafe(queue.put(record), self._loop)
