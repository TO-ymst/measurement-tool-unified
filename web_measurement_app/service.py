from __future__ import annotations

import asyncio
import csv
import datetime as dt
import json
import math
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, TextIO, Tuple

import subprocess

from pydantic import BaseModel, Field, validator

from .logger_core import (
    ADVANCED_EVENT_BSSID_CHANGED,
    ADVANCED_EVENT_PING_TIMEOUT,
    ADVANCED_EVENT_SSH_FAILED,
    CHANNEL_FILTER,
    CONNECTION_EVENT_HEADERS,
    DEFAULT_BAND,
    DEFAULT_INTERVAL,
    DEFAULT_LOG_BASE,
    DEFAULT_MEASUREMENT_MODE,
    DEFAULT_PING_FAIL_VALUE,
    DEFAULT_PING_TARGET,
    DEFAULT_PING_TIMEOUT_MS,
    DEFAULT_PING_STATS_WINDOW_SEC,
    DEFAULT_REMOTE_NEIGHBOR_EVERY,
    DEFAULT_REMOTE_PORT,
    DEFAULT_REMOTE_USER,
    DEFAULT_SSID,
    DEFAULT_TIMEZONE,
    DEFAULT_USE_GATEWAY,
    DEFAULT_USE_SUDO,
    DEFAULT_WIFI_RECONNECT_COOLDOWN_SEC,
    DEFAULT_WIFI_DISCONNECTED_VALUE,
    DEFAULT_SURVEY_ENABLED,
    DEFAULT_SURVEY_INTERVAL_SEC,
    HEADERS,
    IW_HEADERS,
    NEIGHBOR_HEADERS,
    apply_neighbor_summary,
    collect_remote_advanced_snapshot,
    ensure_remote_ssh_key,
    fetch_remote_wifi_state,
    fetch_remote_iw_survey_info,
    fetch_local_iw_station_info,
    fetch_local_iw_survey_info,
    fetch_local_iw_tx_power,
    fetch_wifi_rows,
    get_current_local_wifi_state,
    get_local_wifi_ap_lock,
    get_local_wifi_bssid_lock,
    get_ping_result,
    IS_WINDOWS,
    list_saved_local_wifi_profiles,
    prepare_connection_event_file,
    prepare_neighbor_log_file,
    prepare_log_file,
    prepare_sidecar_file,
    probe_remote_ssh,
    reconnect_local_wifi,
    reconnect_remote_wifi,
    remove_remote_ssh_key,
    resolve_ping_target,
    scan_local_neighbors,
    set_local_wifi_ap_lock,
    set_local_wifi_bssid_lock,
    should_run_neighbor_scan,
    PING_STAT_HEADERS,
    RUNTIME_HEADERS,
    SURVEY_HEADERS,
    switch_local_wifi_ssid,
    switch_local_wifi_bssid,
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
    ping_stats_window_sec: int = Field(default=DEFAULT_PING_STATS_WINDOW_SEC, ge=5, le=300)
    timeout_as_numeric: bool = Field(default=True)
    wifi_disconnected_value: float = Field(default=DEFAULT_WIFI_DISCONNECTED_VALUE)
    auto_reconnect_wifi: bool = Field(default=True)
    wifi_reconnect_cooldown_sec: int = Field(default=DEFAULT_WIFI_RECONNECT_COOLDOWN_SEC, ge=5, le=3600)
    exclusive_ssid_during_measurement: bool = Field(default=True)
    prefix: Optional[str] = None
    log_base: str = Field(default=DEFAULT_LOG_BASE)
    output_dir: str = Field(default_factory=lambda: str(Path(__file__).resolve().parent.parent))
    use_sudo: bool = Field(default=DEFAULT_USE_SUDO)
    sync_time: bool = Field(default=False)
    timezone: str = Field(default=DEFAULT_TIMEZONE)
    retain_rows: int = Field(default=20000, ge=1000, le=200000)
    survey_enabled: bool = Field(default=DEFAULT_SURVEY_ENABLED)
    survey_interval_sec: float = Field(default=DEFAULT_SURVEY_INTERVAL_SEC, ge=1.0, le=3600.0)
    remote_host: Optional[str] = None
    remote_user: str = Field(default=DEFAULT_REMOTE_USER)
    remote_port: int = Field(default=DEFAULT_REMOTE_PORT, ge=1, le=65535)
    remote_identity_file: Optional[str] = None
    remote_enable_neighbor_scan: bool = Field(default=False)
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
    connection_event_file: Optional[str]
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
        self._network_switch_lock = threading.Lock()
        self._local_reconnect_lock = threading.Lock()
        self._local_reconnect_thread: Optional[threading.Thread] = None
        self._neighbor_scan_lock = threading.Lock()
        self._neighbor_scan_thread: Optional[threading.Thread] = None
        self._pending_neighbor_result: Optional[Dict[str, Any]] = None
        self._neighbor_scan_generation = 0
        self._survey_lock = threading.Lock()
        self._survey_thread: Optional[threading.Thread] = None
        self._pending_survey_result: Optional[Dict[str, Any]] = None
        self._latest_survey_result: Optional[Dict[str, Any]] = None
        self._survey_generation = 0
        self._last_survey_started_monotonic = 0.0
        self._current_point = 1
        self._log_index = 0
        self._listeners: Set[asyncio.Queue] = set()
        self._history: Dict[int, Deque[Dict[str, Any]]] = defaultdict(deque)
        self._config: Optional[MeasurementConfig] = None
        self._log_path: Optional[Path] = None
        self._neighbor_log_path: Optional[Path] = None
        self._connection_event_path: Optional[Path] = None
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
        self._bssid_switch_enabled_ssid: Optional[str] = None
        self._last_bssid_switch: Optional[Dict[str, str]] = None
        self._last_wifi_reconnect_attempt = 0.0
        self._measurement_ssid_lock_owned = False
        self._last_iw_counters: Optional[Dict[str, Any]] = None
        self._last_survey_counters: Optional[Dict[str, Any]] = None
        self._ping_window: Deque[Tuple[float, Optional[float]]] = deque()
        self._sample_started_monotonic: Optional[float] = None
        self._previous_sample_started_monotonic: Optional[float] = None
        self._sample_period_ms: Optional[float] = None

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
            self._connection_event_path = prepare_connection_event_file(self._log_path)
            self._neighbor_log_index = 0
            self._neighbor_scan_index = 0
            self._neighbor_scan_generation += 1
            self._pending_neighbor_result = None
            self._survey_generation += 1
            self._pending_survey_result = None
            self._latest_survey_result = None
            self._last_survey_started_monotonic = 0.0
            self._advanced_log_path = (
                prepare_sidecar_file(prefix, f"{config.log_base}_remote_advanced", config.output_dir, ".jsonl")
                if config.measurement_mode == "remote_ssh" and config.remote_advanced_enabled
                else None
            )
            self._last_seen_remote_bssid = None
            self._remote_ping_timeout_streak = 0
            self._remote_timeout_snapshot_taken = False
            self._last_wifi_reconnect_attempt = 0.0
            self._last_iw_counters = None
            self._last_survey_counters = None
            self._ping_window.clear()
            self._sample_started_monotonic = None
            self._previous_sample_started_monotonic = None
            self._sample_period_ms = None
            with self._connection_event_path.open("w", newline="", encoding="utf-8-sig") as event_file:
                csv.writer(event_file).writerow(CONNECTION_EVENT_HEADERS)

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

            self._measurement_ssid_lock_owned = False
            if config.measurement_mode == "local" and config.exclusive_ssid_during_measurement:
                current_wifi = get_current_local_wifi_state(config.use_sudo)
                current_ssid = str(current_wifi.get("ssid", "")).strip()
                if current_ssid != config.ssid:
                    raise RuntimeError(
                        f"Current Wi-Fi SSID is {current_ssid or 'not connected'}; "
                        f"connect to {config.ssid} before starting measurement"
                    )
                existing_lock = get_local_wifi_ap_lock(config.use_sudo)
                if existing_lock["locked"] == "yes":
                    if existing_lock["ssid"] != config.ssid:
                        raise RuntimeError(
                            f"SSID is locked to {existing_lock['ssid']}; release it before measuring {config.ssid}"
                        )
                else:
                    set_local_wifi_ap_lock(config.use_sudo, True)
                    self._measurement_ssid_lock_owned = True

            try:
                self._original_timezone = synchronize_time(config.timezone) if config.sync_time else None
                self._thread = threading.Thread(target=self._run_loop, name="wifi-logger", daemon=True)
                self._thread.start()
            except Exception:
                if self._measurement_ssid_lock_owned:
                    set_local_wifi_ap_lock(config.use_sudo, False)
                    self._measurement_ssid_lock_owned = False
                raise
        return self.status()

    def stop(self) -> MeasurementStatus:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            config = self._config
        with self._survey_lock:
            self._survey_generation += 1
        with self._local_reconnect_lock:
            reconnect_thread = self._local_reconnect_thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        if reconnect_thread and reconnect_thread.is_alive():
            reconnect_thread.join(timeout=5)
        if (
            config
            and config.measurement_mode == "local"
            and self._measurement_ssid_lock_owned
        ):
            try:
                with self._network_switch_lock:
                    set_local_wifi_ap_lock(config.use_sudo, False)
                self._measurement_ssid_lock_owned = False
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"SSID lock restore failed: {exc}"
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
            connection_event_file=str(self._connection_event_path) if self._connection_event_path else None,
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

    def list_local_access_points(self) -> Dict[str, Any]:
        if IS_WINDOWS:
            raise RuntimeError("AP switching is available on Jetson/Linux only")
        with self._lock:
            config = self._config
            enabled_ssid = self._bssid_switch_enabled_ssid
        use_sudo = config.use_sudo if config and config.measurement_mode == "local" else DEFAULT_USE_SUDO
        with self._network_switch_lock:
            current = get_current_local_wifi_state(use_sudo)
            access_points = scan_local_neighbors(use_sudo, None)
            saved_profiles = list_saved_local_wifi_profiles(use_sudo)
            saved_ssids = sorted({profile["ssid"] for profile in saved_profiles})
            try:
                bssid_lock = get_local_wifi_bssid_lock(use_sudo)
            except RuntimeError:
                bssid_lock = {"connection": "", "bssid": ""}
            try:
                ap_lock = get_local_wifi_ap_lock(use_sudo)
            except RuntimeError:
                ap_lock = {
                    "connection": "",
                    "ssid": "",
                    "priority": "0",
                    "locked": "no",
                    "disabled_count": "0",
                }
        return {
            "current": current,
            "access_points": access_points,
            "saved_ssids": saved_ssids,
            "saved_profiles": saved_profiles,
            "bssid_switch_enabled_ssid": enabled_ssid,
            "bssid_lock": bssid_lock,
            "ap_lock": ap_lock,
        }

    def switch_local_ap(self, ssid: str, password: Optional[str] = None) -> Dict[str, Any]:
        if IS_WINDOWS:
            raise RuntimeError("AP switching is available on Jetson/Linux only")
        normalized_ssid = ssid.strip()
        if not normalized_ssid:
            raise RuntimeError("SSID is required")
        with self._lock:
            config = self._config
        if config and config.measurement_mode != "local":
            raise RuntimeError("AP switching is available in local measurement mode only")
        use_sudo = config.use_sudo if config else DEFAULT_USE_SUDO

        with self._network_switch_lock:
            before = get_current_local_wifi_state(use_sudo)
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            started_monotonic = time.monotonic()
            try:
                connected = switch_local_wifi_ssid(use_sudo, normalized_ssid, password)
                self._refresh_local_ping_target(config)
                with self._lock:
                    self._bssid_switch_enabled_ssid = normalized_ssid
                    self._last_bssid_switch = None
                self._write_connection_event(
                    started_at,
                    "ap_switch",
                    normalized_ssid,
                    "",
                    connected,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "success",
                    f"from_ssid={before.get('ssid', '')};from_bssid={before.get('bssid', '')}",
                )
                return {"ok": True, "before": before, "connected": connected}
            except Exception as exc:  # noqa: BLE001
                self._write_connection_event(
                    started_at,
                    "ap_switch",
                    normalized_ssid,
                    "",
                    {},
                    round((time.monotonic() - started_monotonic) * 1000),
                    "failed",
                    str(exc),
                )
                raise

    def fix_local_ap(self, ssid: Optional[str] = None) -> Dict[str, Any]:
        if IS_WINDOWS:
            raise RuntimeError("AP locking is available on Jetson/Linux only")
        normalized_ssid = (ssid or "").strip()
        with self._lock:
            config = self._config
        use_sudo = config.use_sudo if config and config.measurement_mode == "local" else DEFAULT_USE_SUDO
        with self._network_switch_lock:
            current = get_current_local_wifi_state(use_sudo)
            current_ssid = str(current.get("ssid", "")).strip()
            if normalized_ssid and current_ssid != normalized_ssid:
                current = switch_local_wifi_ssid(use_sudo, normalized_ssid)
                current_ssid = str(current.get("ssid", "")).strip()
                self._refresh_local_ping_target(config)
            if not current_ssid:
                raise RuntimeError("Connect to the target SSID before locking it")
            if normalized_ssid and current_ssid != normalized_ssid:
                raise RuntimeError("Connected SSID verification failed")
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            started_monotonic = time.monotonic()
            try:
                lock_info = set_local_wifi_ap_lock(use_sudo, True)
                self._write_connection_event(
                    started_at,
                    "ssid_lock",
                    current_ssid,
                    "",
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "success",
                    (
                        f"connection={lock_info.get('connection', '')};"
                        f"disabled_profiles={lock_info.get('disabled_count', '0')}"
                    ),
                )
                return {"ok": True, "connected": current, "ap_lock": lock_info}
            except Exception as exc:  # noqa: BLE001
                self._write_connection_event(
                    started_at,
                    "ssid_lock",
                    current_ssid,
                    "",
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "failed",
                    str(exc),
                )
                raise

    def clear_local_ap_fix(self) -> Dict[str, Any]:
        if IS_WINDOWS:
            raise RuntimeError("AP locking is available on Jetson/Linux only")
        with self._lock:
            config = self._config
        use_sudo = config.use_sudo if config and config.measurement_mode == "local" else DEFAULT_USE_SUDO
        with self._network_switch_lock:
            current = get_current_local_wifi_state(use_sudo)
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            started_monotonic = time.monotonic()
            try:
                lock_info = set_local_wifi_ap_lock(use_sudo, False)
                self._write_connection_event(
                    started_at,
                    "ssid_unlock",
                    str(current.get("ssid", "")),
                    "",
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "success",
                    "restored_saved_wifi_autoconnect",
                )
                return {"ok": True, "connected": current, "ap_lock": lock_info}
            except Exception as exc:  # noqa: BLE001
                self._write_connection_event(
                    started_at,
                    "ssid_unlock",
                    str(current.get("ssid", "")),
                    "",
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "failed",
                    str(exc),
                )
                raise

    def switch_local_bssid(self, ssid: str, bssid: str) -> Dict[str, Any]:
        if IS_WINDOWS:
            raise RuntimeError("BSSID switching is available on Jetson/Linux only")
        with self._lock:
            config = self._config
        if config and config.measurement_mode != "local":
            raise RuntimeError("BSSID switching is available in local measurement mode only")
        use_sudo = config.use_sudo if config else DEFAULT_USE_SUDO

        with self._network_switch_lock:
            before = get_current_local_wifi_state(use_sudo)
            if str(before.get("ssid", "")).strip() != ssid.strip():
                raise RuntimeError("Current SSID does not match the selected BSSID")
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            started_monotonic = time.monotonic()
            try:
                connected = switch_local_wifi_bssid(use_sudo, ssid, bssid)
                self._refresh_local_ping_target(config)
                with self._lock:
                    self._last_bssid_switch = {
                        "ssid": str(connected.get("ssid", "")),
                        "bssid": str(connected.get("bssid", "")).lower(),
                    }
                self._write_connection_event(
                    started_at,
                    "bssid_switch",
                    ssid,
                    bssid,
                    connected,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "success",
                    f"from={before.get('bssid', '')}",
                )
                return {
                    "ok": True,
                    "before": before,
                    "connected": connected,
                    "ping_target": self._ping_target_info[0] if self._ping_target_info else "",
                }
            except Exception as exc:  # noqa: BLE001
                self._write_connection_event(
                    started_at,
                    "bssid_switch",
                    ssid,
                    bssid,
                    {},
                    round((time.monotonic() - started_monotonic) * 1000),
                    "failed",
                    str(exc),
                )
                raise

    def fix_local_bssid(self) -> Dict[str, Any]:
        if IS_WINDOWS:
            raise RuntimeError("BSSID locking is available on Jetson/Linux only")
        with self._lock:
            config = self._config
        if config and config.measurement_mode != "local":
            raise RuntimeError("BSSID locking is available in local measurement mode only")
        use_sudo = config.use_sudo if config else DEFAULT_USE_SUDO

        with self._network_switch_lock:
            current = get_current_local_wifi_state(use_sudo)
            current_ssid = str(current.get("ssid", "")).strip()
            current_bssid = str(current.get("bssid", "")).lower()
            if not current_ssid or not current_bssid:
                raise RuntimeError("No connected BSSID was found")
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            started_monotonic = time.monotonic()
            try:
                lock_info = set_local_wifi_bssid_lock(use_sudo, current_bssid)
                self._write_connection_event(
                    started_at,
                    "bssid_lock",
                    current_ssid,
                    current_bssid,
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "success",
                    f"connection={lock_info.get('connection', '')}",
                )
                return {"ok": True, "connected": current, "bssid_lock": lock_info}
            except Exception as exc:  # noqa: BLE001
                self._write_connection_event(
                    started_at,
                    "bssid_lock",
                    last_switch["ssid"],
                    last_switch["bssid"],
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "failed",
                    str(exc),
                )
                raise

    def clear_local_bssid_fix(self) -> Dict[str, Any]:
        if IS_WINDOWS:
            raise RuntimeError("BSSID locking is available on Jetson/Linux only")
        with self._lock:
            config = self._config
        if config and config.measurement_mode != "local":
            raise RuntimeError("BSSID locking is available in local measurement mode only")
        use_sudo = config.use_sudo if config else DEFAULT_USE_SUDO
        with self._network_switch_lock:
            current = get_current_local_wifi_state(use_sudo)
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            started_monotonic = time.monotonic()
            try:
                lock_info = set_local_wifi_bssid_lock(use_sudo, None)
                self._write_connection_event(
                    started_at,
                    "bssid_unlock",
                    str(current.get("ssid", "")),
                    str(current.get("bssid", "")),
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "success",
                    f"connection={lock_info.get('connection', '')}",
                )
                return {"ok": True, "connected": current, "bssid_lock": lock_info}
            except Exception as exc:  # noqa: BLE001
                self._write_connection_event(
                    started_at,
                    "bssid_unlock",
                    str(current.get("ssid", "")),
                    str(current.get("bssid", "")),
                    current,
                    round((time.monotonic() - started_monotonic) * 1000),
                    "failed",
                    str(exc),
                )
                raise

    def _refresh_local_ping_target(self, config: Optional[MeasurementConfig]) -> None:
        if not config or not config.auto_gateway:
            return
        self._ping_target_info = resolve_ping_target(
            config.ping_target, config.auto_gateway, DEFAULT_PING_TARGET
        )

    def _write_connection_event(
        self,
        timestamp: str,
        event: str,
        ssid: str,
        bssid: str,
        connected: Dict[str, Any],
        duration_ms: int,
        result: str,
        details: str,
    ) -> None:
        if not self._connection_event_path:
            return
        with self._connection_event_path.open("a", newline="", encoding="utf-8") as event_file:
            csv.writer(event_file).writerow(
                [
                    timestamp,
                    event,
                    ssid,
                    bssid,
                    connected.get("ssid", ""),
                    connected.get("bssid", ""),
                    connected.get("channel", ""),
                    duration_ms,
                    result,
                    details,
                ]
            )

    def _can_attempt_wifi_reconnect(self, config: MeasurementConfig) -> bool:
        if not config.auto_reconnect_wifi or not config.ssid:
            return False
        now = time.monotonic()
        if now - self._last_wifi_reconnect_attempt < config.wifi_reconnect_cooldown_sec:
            return False
        self._last_wifi_reconnect_attempt = now
        return True

    def _local_reconnect_running(self) -> bool:
        with self._local_reconnect_lock:
            return bool(self._local_reconnect_thread and self._local_reconnect_thread.is_alive())

    def _schedule_local_wifi_reconnect(self, config: MeasurementConfig) -> None:
        if self._stop_event.is_set() or not self._can_attempt_wifi_reconnect(config):
            return
        with self._local_reconnect_lock:
            if self._local_reconnect_thread and self._local_reconnect_thread.is_alive():
                return
            thread = threading.Thread(
                target=self._reconnect_local_wifi_worker,
                args=(config,),
                name="wifi-reconnect",
                daemon=True,
            )
            self._local_reconnect_thread = thread
            thread.start()

    def _reconnect_local_wifi_worker(self, config: MeasurementConfig) -> None:
        started = time.monotonic()
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
        current: Dict[str, Any] = {}
        try:
            with self._network_switch_lock:
                try:
                    current = get_current_local_wifi_state(config.use_sudo)
                except RuntimeError:
                    current = {}
                # reconnect_local_wifi also verifies the saved BSSID lock. Do
                # not accept a same-SSID connection to a different AP here.
                connected = reconnect_local_wifi(config.use_sudo, config.ssid)
                self._refresh_local_ping_target(config)
                self._write_connection_event(
                    timestamp, "wifi_reconnect", config.ssid, "", connected,
                    round((time.monotonic() - started) * 1000), "success", "saved_profile",
                )
        except Exception as exc:  # noqa: BLE001
            self._write_connection_event(
                timestamp, "wifi_reconnect", config.ssid, "", current,
                round((time.monotonic() - started) * 1000), "failed", str(exc),
            )
        finally:
            with self._local_reconnect_lock:
                if self._local_reconnect_thread is threading.current_thread():
                    self._local_reconnect_thread = None

    def _ensure_remote_wifi_connected(
        self, config: MeasurementConfig, current: Dict[str, Any]
    ) -> Dict[str, Any]:
        if str(current.get("ssid", "")) == config.ssid or not self._can_attempt_wifi_reconnect(config):
            return current

        started = time.monotonic()
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            connected = reconnect_remote_wifi(
                host=config.remote_host or "", user=config.remote_user, port=config.remote_port,
                identity_file=config.remote_identity_file, ssid=config.ssid,
            )
            self._write_connection_event(
                timestamp, "remote_wifi_reconnect", config.ssid, "", connected,
                round((time.monotonic() - started) * 1000), "success", "saved_profile",
            )
            return connected
        except Exception as exc:  # noqa: BLE001
            self._write_connection_event(
                timestamp, "remote_wifi_reconnect", config.ssid, "", current,
                round((time.monotonic() - started) * 1000), "failed", str(exc),
            )
            return current

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

    def _begin_sample(self) -> None:
        started = time.monotonic()
        previous = self._previous_sample_started_monotonic
        self._sample_started_monotonic = started
        self._sample_period_ms = (started - previous) * 1000 if previous is not None else None
        self._previous_sample_started_monotonic = started

    @staticmethod
    def _format_metric(value: Optional[float]) -> str:
        return f"{value:.3f}" if value is not None else ""

    @staticmethod
    def _percentile(values: List[float], percentile: float) -> Optional[float]:
        if not values:
            return None
        ordered = sorted(values)
        position = (len(ordered) - 1) * percentile
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    def _ping_stat_columns(self, ping_value: Any, ping_status: Any, config: MeasurementConfig) -> List[str]:
        now = time.monotonic()
        status = str(ping_status or "")
        rtt: Optional[float] = None
        if status == "ok":
            try:
                candidate = float(str(ping_value).strip())
                if math.isfinite(candidate):
                    rtt = candidate
            except (TypeError, ValueError):
                pass
        if status in {"ok", "ping_timeout", "timeout"}:
            self._ping_window.append((now, rtt))
        cutoff = now - config.ping_stats_window_sec
        while self._ping_window and self._ping_window[0][0] < cutoff:
            self._ping_window.popleft()

        samples = list(self._ping_window)
        successful = [value for _timestamp, value in samples if value is not None]
        loss_rate = ((len(samples) - len(successful)) / len(samples) * 100) if samples else None
        jitter_values = [
            abs(successful[index] - successful[index - 1])
            for index in range(1, len(successful))
        ]
        return [
            str(len(samples)),
            str(len(successful)),
            self._format_metric(loss_rate),
            self._format_metric(sum(successful) / len(successful) if successful else None),
            self._format_metric(self._percentile(successful, 0.5)),
            self._format_metric(min(successful) if successful else None),
            self._format_metric(max(successful) if successful else None),
            self._format_metric(self._percentile(successful, 0.95)),
            self._format_metric(self._percentile(successful, 0.99)),
            self._format_metric(sum(jitter_values) / len(jitter_values) if jitter_values else None),
        ]

    def _schedule_survey(self, config: MeasurementConfig) -> None:
        if not config.survey_enabled:
            return
        now = time.monotonic()
        with self._survey_lock:
            if self._survey_thread and self._survey_thread.is_alive():
                return
            if now - self._last_survey_started_monotonic < config.survey_interval_sec:
                return
            self._last_survey_started_monotonic = now
            generation = self._survey_generation
            self._survey_thread = threading.Thread(
                target=self._survey_worker,
                args=(config, generation),
                daemon=True,
                name="wifi-iw-survey",
            )
            self._survey_thread.start()

    def _survey_worker(self, config: MeasurementConfig, generation: int) -> None:
        try:
            if config.measurement_mode == "remote_ssh":
                info = fetch_remote_iw_survey_info(
                    host=config.remote_host or "",
                    user=config.remote_user,
                    port=config.remote_port,
                    identity_file=config.remote_identity_file,
                )
            else:
                info = fetch_local_iw_survey_info()
            result = {"info": info, "captured_monotonic": time.monotonic()}
        except Exception:  # noqa: BLE001
            result = {"info": {}, "captured_monotonic": time.monotonic()}
        with self._survey_lock:
            if generation == self._survey_generation:
                self._pending_survey_result = result

    @staticmethod
    def _survey_counter(info: Dict[str, Any], key: str) -> Optional[int]:
        try:
            return int(str(info.get(key, "")).strip())
        except (TypeError, ValueError):
            return None

    def _survey_columns(self, config: MeasurementConfig) -> List[str]:
        empty = ["" for _header in SURVEY_HEADERS]
        if not config.survey_enabled:
            return empty
        with self._survey_lock:
            pending = self._pending_survey_result
            self._pending_survey_result = None
        updated = pending is not None
        if pending is not None:
            self._latest_survey_result = pending
        latest = self._latest_survey_result
        if not latest:
            return empty

        info = dict(latest.get("info") or {})
        if str(info.get("SurveySampleValid", "")) != "yes":
            return empty
        captured = float(latest.get("captured_monotonic") or time.monotonic())
        age_ms = max(0.0, (time.monotonic() - captured) * 1000)
        values = {
            "SurveySampleValid": "yes",
            "SurveyUpdated": "yes" if updated else "no",
            "SurveyAgeMs": self._format_metric(age_ms),
            "SurveyFrequencyMhz": str(info.get("SurveyFrequencyMhz", "") or ""),
            "SurveyNoiseDbm": str(info.get("SurveyNoiseDbm", "") or ""),
            "SurveyActiveMsDelta": "",
            "SurveyBusyMsDelta": "",
            "SurveyRxMsDelta": "",
            "SurveyTxMsDelta": "",
            "SurveyBusyRatePct": "",
        }
        if updated:
            current = {
                "frequency": values["SurveyFrequencyMhz"],
                "active": self._survey_counter(info, "SurveyActiveMsTotal"),
                "busy": self._survey_counter(info, "SurveyBusyMsTotal"),
                "rx": self._survey_counter(info, "SurveyRxMsTotal"),
                "tx": self._survey_counter(info, "SurveyTxMsTotal"),
            }
            previous = self._last_survey_counters
            if previous and previous.get("frequency") == current["frequency"]:
                deltas: Dict[str, int] = {}
                for name in ("active", "busy", "rx", "tx"):
                    old = previous.get(name)
                    new = current.get(name)
                    if old is None or new is None or new < old:
                        deltas = {}
                        break
                    deltas[name] = new - old
                if deltas:
                    values["SurveyActiveMsDelta"] = str(deltas["active"])
                    values["SurveyBusyMsDelta"] = str(deltas["busy"])
                    values["SurveyRxMsDelta"] = str(deltas["rx"])
                    values["SurveyTxMsDelta"] = str(deltas["tx"])
                    if deltas["active"] > 0:
                        values["SurveyBusyRatePct"] = self._format_metric(
                            deltas["busy"] / deltas["active"] * 100
                        )
            self._last_survey_counters = current
        return [values[header] for header in SURVEY_HEADERS]

    def _append_runtime_diagnostics(self, log_line: List[Any]) -> None:
        config = self._config
        if not config:
            log_line.extend(["" for _header in PING_STAT_HEADERS + RUNTIME_HEADERS + SURVEY_HEADERS])
            return
        log_line.extend(self._ping_stat_columns(log_line[12], log_line[13], config))
        started = self._sample_started_monotonic
        duration_ms = (time.monotonic() - started) * 1000 if started is not None else None
        period_ms = self._sample_period_ms
        overrun_ms = (
            max(0.0, duration_ms - config.interval * 1000)
            if duration_ms is not None
            else None
        )
        log_line.extend(
            [
                self._format_metric(duration_ms),
                self._format_metric(period_ms),
                self._format_metric(overrun_ms),
            ]
        )
        log_line.extend(self._survey_columns(config))

    def _run_loop(self) -> None:
        assert self._config and self._log_path and self._neighbor_log_path and self._ping_target_info
        config = self._config
        target_ip, _target_source = self._ping_target_info
        sample_no = 0

        try:
            with open(self._log_path, "w", newline="", encoding="utf-8-sig") as csv_file:
                with open(self._neighbor_log_path, "w", newline="", encoding="utf-8-sig") as neighbor_file:
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
                            self._begin_sample()
                            self._schedule_survey(config)
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
                                target_ip = (
                                    self._ping_target_info[0]
                                    if self._ping_target_info and self._ping_target_info[0]
                                    else target_ip
                                )
                                if self._local_reconnect_running():
                                    self._write_local_disconnected_record(
                                        writer, csv_file, config, target_ip, "wifi_reconnect_in_progress"
                                    )
                                elif self._network_switch_lock.acquire(blocking=False):
                                    try:
                                        self._run_local_iteration(
                                            writer, csv_file, neighbor_writer, config, target_ip, sample_no
                                        )
                                    finally:
                                        self._network_switch_lock.release()
                                else:
                                    self._write_local_disconnected_record(
                                        writer, csv_file, config, target_ip, "network_switch_in_progress"
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
            if str(remote_row.get("ssid", "")) != config.ssid:
                reconnected = self._ensure_remote_wifi_connected(config, remote_row)
                if str(reconnected.get("ssid", "")) == config.ssid:
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
            iw_info = self._prepare_iw_info(row, row.get("bssid", ""))
            self._append_iw_columns(log_line, iw_info)
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
            self._last_iw_counters = None
            self._append_iw_columns(log_line, {})
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

        neighbor_result = self._take_neighbor_scan_result()
        if neighbor_result:
            neighbor_rows = neighbor_result.get("rows", [])
            scan_error = str(neighbor_result.get("error", "") or "")
            if scan_error:
                error_message = error_message or scan_error
            else:
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

        if (
            config.remote_enable_neighbor_scan
            and should_run_neighbor_scan(sample_no, config.remote_neighbor_every)
        ):
            self._schedule_neighbor_scan(config.use_sudo, config.remote_neighbor_ssid)

        if wifi_rows:
            for row in wifi_rows:
                icmp_seq, ttl, time_ms, ping_status = get_ping_result(
                    target_ip,
                    config.timeout_as_numeric,
                    config.ping_fail_value,
                    config.ping_timeout_ms,
                )
                iw_info = fetch_local_iw_station_info()
                iw_info["IwTxPowerDbm"] = fetch_local_iw_tx_power()
                iw_info = self._prepare_iw_info(iw_info, row.get("bssid", ""))
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
                self._append_iw_columns(log_line, iw_info)
                self._write_and_publish_record(writer, csv_file, log_line, error_message, config.retain_rows)
        else:
            self._schedule_local_wifi_reconnect(config)
            self._write_local_disconnected_record(
                writer, csv_file, config, target_ip, error_message or "wifi_disconnected"
            )

    def _schedule_neighbor_scan(self, use_sudo: bool, target_ssid: Optional[str]) -> None:
        with self._neighbor_scan_lock:
            if self._neighbor_scan_thread and self._neighbor_scan_thread.is_alive():
                return
            if self._pending_neighbor_result is not None:
                return
            generation = self._neighbor_scan_generation
            self._neighbor_scan_thread = threading.Thread(
                target=self._neighbor_scan_worker,
                args=(use_sudo, target_ssid, generation),
                daemon=True,
                name="wifi-neighbor-scan",
            )
            self._neighbor_scan_thread.start()

    def _neighbor_scan_worker(
        self,
        use_sudo: bool,
        target_ssid: Optional[str],
        generation: int,
    ) -> None:
        try:
            result: Dict[str, Any] = {
                "rows": scan_local_neighbors(use_sudo, target_ssid),
                "error": "",
            }
        except RuntimeError as exc:
            result = {"rows": [], "error": str(exc)}
        with self._neighbor_scan_lock:
            if generation == self._neighbor_scan_generation:
                self._pending_neighbor_result = result

    def _take_neighbor_scan_result(self) -> Optional[Dict[str, Any]]:
        with self._neighbor_scan_lock:
            result = self._pending_neighbor_result
            self._pending_neighbor_result = None
            return result

    def _write_local_disconnected_record(
        self,
        writer: csv.writer,
        csv_file,
        config: MeasurementConfig,
        target_ip: str,
        error_message: str,
    ) -> None:
        date_str, time_str, point_value = self._timestamp_and_point()
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
            "",
            "",
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
            error_message,
        ]
        self._last_iw_counters = None
        self._append_iw_columns(log_line, {})
        self._write_and_publish_record(
            writer,
            csv_file,
            log_line,
            "Wi-Fi disconnected placeholder recorded",
            config.retain_rows,
        )

    @staticmethod
    def _normalize_bssid(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _counter_value(info: Dict[str, Any], key: str) -> Optional[int]:
        try:
            return int(str(info.get(key, "")).strip())
        except (TypeError, ValueError):
            return None

    def _prepare_iw_info(self, info: Dict[str, Any], expected_bssid: Any) -> Dict[str, Any]:
        prepared = {header: str(info.get(header, "") or "") for header in IW_HEADERS}
        if prepared["IwSampleValid"] != "yes":
            self._last_iw_counters = None
            return prepared

        expected = self._normalize_bssid(expected_bssid)
        station = self._normalize_bssid(prepared["IwStationBssid"])
        if not expected or expected != station:
            prepared = {header: "" for header in IW_HEADERS}
            self._last_iw_counters = None
            return prepared

        current = {
            "bssid": station,
            "tx_packets": self._counter_value(prepared, "IwTxPacketsTotal"),
            "tx_retries": self._counter_value(prepared, "IwTxRetriesTotal"),
            "tx_failed": self._counter_value(prepared, "IwTxFailedTotal"),
        }
        previous = self._last_iw_counters
        if previous and previous.get("bssid") == station:
            deltas: Dict[str, int] = {}
            for name in ("tx_packets", "tx_retries", "tx_failed"):
                old_value = previous.get(name)
                new_value = current.get(name)
                if old_value is None or new_value is None or new_value < old_value:
                    deltas = {}
                    break
                deltas[name] = new_value - old_value
            if deltas:
                prepared["IwTxPacketsDelta"] = str(deltas["tx_packets"])
                prepared["IwTxRetriesDelta"] = str(deltas["tx_retries"])
                prepared["IwTxFailedDelta"] = str(deltas["tx_failed"])
                if deltas["tx_packets"] > 0:
                    prepared["IwTxRetryRatePct"] = f'{deltas["tx_retries"] / deltas["tx_packets"] * 100:.3f}'
                    prepared["IwTxFailedRatePct"] = f'{deltas["tx_failed"] / deltas["tx_packets"] * 100:.3f}'
        self._last_iw_counters = current
        return prepared

    @staticmethod
    def _append_iw_columns(log_line: List[Any], info: Dict[str, Any]) -> None:
        log_line.extend(info.get(header, "") for header in IW_HEADERS)

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
        self._append_runtime_diagnostics(log_line)
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
