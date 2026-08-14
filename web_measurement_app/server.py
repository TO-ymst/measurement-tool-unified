from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .logger_core import (
    CHANNEL_FILTER,
    DEFAULT_BAND,
    DEFAULT_INTERVAL,
    DEFAULT_LOG_BASE,
    DEFAULT_MEASUREMENT_MODE,
    DEFAULT_PING_FAIL_VALUE,
    DEFAULT_PING_STATS_WINDOW_SEC,
    DEFAULT_PING_TIMEOUT_MS,
    DEFAULT_REMOTE_NEIGHBOR_EVERY,
    DEFAULT_REMOTE_PORT,
    DEFAULT_REMOTE_USER,
    DEFAULT_SSID,
    DEFAULT_TIMEZONE,
    DEFAULT_USE_SUDO,
    DEFAULT_SURVEY_ENABLED,
    DEFAULT_SURVEY_INTERVAL_SEC,
    DEFAULT_WIFI_RECONNECT_COOLDOWN_SEC,
    DEFAULT_WIFI_DISCONNECTED_VALUE,
    IS_WINDOWS,
    ensure_remote_ssh_key,
    get_current_ssid,
    list_available_ssids,
    probe_remote_ssh,
    remove_remote_ssh_key,
)
from .service import MeasurementConfig, MeasurementService

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Wi-Fi Measurement Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

service = MeasurementService()


class HidePointRequest(BaseModel):
    point_id: int
    source_csv: Optional[str] = None


class RemoteSetupRequest(BaseModel):
    remote_host: str
    remote_user: str = DEFAULT_REMOTE_USER
    remote_port: int = DEFAULT_REMOTE_PORT
    remote_identity_file: Optional[str] = None
    remote_setup_ssh_key: bool = True
    remote_cleanup_ssh_key: bool = True
    remote_delete_local_key: bool = True
    remote_ssh_key_comment: Optional[str] = None


class BssidSwitchRequest(BaseModel):
    ssid: str
    bssid: str
    acknowledged_usb_or_lan: bool = False


class ApSwitchRequest(BaseModel):
    ssid: str
    password: Optional[str] = None
    acknowledged_usb_or_lan: bool = False


class BssidLockRequest(BaseModel):
    acknowledged_usb_or_lan: bool = False
    ssid: Optional[str] = None


def _resolve_source_csv_path(source_csv: Optional[str]) -> Path:
    if source_csv:
        path = Path(source_csv).expanduser()
    else:
        status = service.status()
        if not status.log_file:
            raise HTTPException(status_code=400, detail="No source CSV provided and no active log file")
        path = Path(status.log_file)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Source CSV not found: {path}")
    return path


def _next_corrected_csv_path(source_path: Path) -> Path:
    stem = source_path.stem
    suffix = source_path.suffix
    parent = source_path.parent
    max_ver = 0
    for candidate in parent.glob(f"{stem}_corrected_v*{suffix}"):
        token = candidate.stem.rsplit("_v", 1)
        if len(token) != 2:
            continue
        try:
            max_ver = max(max_ver, int(token[1]))
        except ValueError:
            continue
    return parent / f"{stem}_corrected_v{max_ver + 1}{suffix}"


def _load_or_init_corrections(corrections_path: Path) -> Dict[str, Any]:
    if corrections_path.exists():
        try:
            with corrections_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("hidden_points", [])
                data.setdefault("events", [])
                return data
        except Exception:
            pass
    return {"hidden_points": [], "events": []}


@app.on_event("startup")
async def startup_event() -> None:
    loop = asyncio.get_running_loop()
    service.bind_loop(loop)


@app.get("/", response_class=FileResponse)
async def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/defaults")
async def read_defaults() -> Dict[str, Any]:
    current_ssid = get_current_ssid(use_sudo=DEFAULT_USE_SUDO)
    ssid_options = list_available_ssids(use_sudo=DEFAULT_USE_SUDO)
    return {
        "measurement_mode": DEFAULT_MEASUREMENT_MODE,
        "ssid": current_ssid or "",
        "ssid_options": ssid_options,
        "band": DEFAULT_BAND,
        "channel_min": CHANNEL_FILTER[DEFAULT_BAND]["min"],
        "channel_max": CHANNEL_FILTER[DEFAULT_BAND]["max"],
        "auto_gateway": True,
        "interval": DEFAULT_INTERVAL,
        "ping_fail_value": DEFAULT_PING_FAIL_VALUE,
        "ping_timeout_ms": DEFAULT_PING_TIMEOUT_MS,
        "ping_stats_window_sec": DEFAULT_PING_STATS_WINDOW_SEC,
        "wifi_disconnected_value": DEFAULT_WIFI_DISCONNECTED_VALUE,
        "auto_reconnect_wifi": True,
        "wifi_reconnect_cooldown_sec": DEFAULT_WIFI_RECONNECT_COOLDOWN_SEC,
        "exclusive_ssid_during_measurement": True,
        "survey_enabled": DEFAULT_SURVEY_ENABLED,
        "survey_interval_sec": DEFAULT_SURVEY_INTERVAL_SEC,
        "log_base": DEFAULT_LOG_BASE,
        "output_dir": str(BASE_DIR.parent),
        "timezone": DEFAULT_TIMEZONE,
        "timezone_options": ["Asia/Tokyo", "Etc/GMT"],
        "bands": CHANNEL_FILTER,
        "remote_host": "",
        "remote_user": DEFAULT_REMOTE_USER,
        "remote_port": DEFAULT_REMOTE_PORT,
        "remote_identity_file": "",
        "remote_enable_neighbor_scan": False,
        "remote_neighbor_every": DEFAULT_REMOTE_NEIGHBOR_EVERY,
        "remote_neighbor_ssid": "",
        "remote_setup_ssh_key": True,
        "remote_cleanup_ssh_key": True,
        "remote_delete_local_key": True,
        "remote_ssh_key_comment": "",
        "remote_advanced_enabled": False,
        "remote_advanced_include_neighbor": False,
        "remote_advanced_include_routes": False,
        "remote_advanced_include_ip_addr": False,
        "remote_advanced_include_wifi_details": False,
        "remote_advanced_include_journal": False,
        "remote_advanced_snapshot_on_bssid_change": False,
        "remote_advanced_snapshot_on_ping_timeout": False,
        "remote_advanced_ping_timeout_streak": 1,
        "remote_advanced_max_output_chars": 12000,
        "local_bssid_switch_supported": not IS_WINDOWS,
    }


@app.post("/api/start")
async def start_measurement(config: MeasurementConfig):
    try:
        status = service.start(config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status


@app.post("/api/remote/prepare")
async def prepare_remote_measurement(payload: RemoteSetupRequest):
    try:
        identity_file = payload.remote_identity_file
        if payload.remote_setup_ssh_key:
            identity_file = ensure_remote_ssh_key(
                host=payload.remote_host,
                user=payload.remote_user,
                port=payload.remote_port,
                identity_file=payload.remote_identity_file,
                comment=payload.remote_ssh_key_comment,
            )
        probe_result = probe_remote_ssh(
            host=payload.remote_host,
            user=payload.remote_user,
            port=payload.remote_port,
            identity_file=identity_file,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "identity_file": identity_file or "",
        "probe_result": probe_result,
        "message": f"SSH準備完了: {payload.remote_user}@{payload.remote_host}",
    }


@app.post("/api/remote/cleanup")
async def cleanup_remote_measurement(payload: RemoteSetupRequest):
    try:
        remove_remote_ssh_key(
            host=payload.remote_host,
            user=payload.remote_user,
            port=payload.remote_port,
            identity_file=payload.remote_identity_file,
            delete_local=payload.remote_delete_local_key,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": "SSH鍵を削除しました。"}


@app.post("/api/stop")
async def stop_measurement():
    status = service.stop()
    return status


@app.get("/api/local/access-points")
async def list_local_access_points():
    try:
        return service.list_local_access_points()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local/switch-bssid")
async def switch_local_bssid(payload: BssidSwitchRequest):
    if not payload.acknowledged_usb_or_lan:
        raise HTTPException(status_code=400, detail="Confirm that the dashboard is connected through USB or wired LAN")
    try:
        return service.switch_local_bssid(payload.ssid, payload.bssid)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local/switch-ap")
async def switch_local_ap(payload: ApSwitchRequest):
    if not payload.acknowledged_usb_or_lan:
        raise HTTPException(status_code=400, detail="Confirm that the dashboard is connected through USB or wired LAN")
    try:
        return service.switch_local_ap(payload.ssid, payload.password)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local/fix-bssid")
async def fix_local_bssid(payload: BssidLockRequest):
    if not payload.acknowledged_usb_or_lan:
        raise HTTPException(status_code=400, detail="Confirm that the dashboard is connected through USB or wired LAN")
    try:
        return service.fix_local_bssid()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local/fix-ap")
async def fix_local_ap(payload: BssidLockRequest):
    if not payload.acknowledged_usb_or_lan:
        raise HTTPException(status_code=400, detail="Confirm that the dashboard is connected through USB or wired LAN")
    try:
        return service.fix_local_ap(payload.ssid)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local/clear-ap-fix")
async def clear_local_ap_fix(payload: BssidLockRequest):
    if not payload.acknowledged_usb_or_lan:
        raise HTTPException(status_code=400, detail="Confirm that the dashboard is connected through USB or wired LAN")
    try:
        return service.clear_local_ap_fix()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local/clear-bssid-fix")
async def clear_local_bssid_fix(payload: BssidLockRequest):
    if not payload.acknowledged_usb_or_lan:
        raise HTTPException(status_code=400, detail="Confirm that the dashboard is connected through USB or wired LAN")
    try:
        return service.clear_local_bssid_fix()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/advance-point")
async def advance_point():
    try:
        payload = service.advance_point()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payload


@app.post("/api/revert-point")
async def revert_point():
    try:
        payload = service.revert_point()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payload


@app.get("/api/status")
async def get_status():
    return service.status()


@app.get("/api/logs/{point_id}")
async def fetch_logs(point_id: int):
    return service.get_logs(point_id)


@app.post("/api/corrections/hide-point")
async def hide_point_and_generate_csv(payload: HidePointRequest):
    source_path = _resolve_source_csv_path(payload.source_csv)
    corrected_csv_path = _next_corrected_csv_path(source_path)
    corrections_path = source_path.with_name(f"{source_path.stem}_corrections.json")

    corrections = _load_or_init_corrections(corrections_path)
    hidden_points = {int(v) for v in corrections.get("hidden_points", []) if str(v).isdigit()}
    hidden_points.add(int(payload.point_id))
    corrections["hidden_points"] = sorted(hidden_points)
    corrections["events"].append(
        {"action": "hide_point", "point_id": int(payload.point_id), "at": datetime.now().isoformat(timespec="seconds")}
    )

    with source_path.open("r", encoding="utf-8-sig", newline="") as src, corrected_csv_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        fieldnames = reader.fieldnames or []
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            point_text = str(row.get("Point", "")).strip()
            try:
                point_value = int(point_text)
            except ValueError:
                point_value = None
            if point_value in hidden_points:
                continue
            writer.writerow(row)

    with corrections_path.open("w", encoding="utf-8") as fh:
        json.dump(corrections, fh, ensure_ascii=False, indent=2)

    return {
        "source_csv": str(source_path),
        "corrected_csv": str(corrected_csv_path),
        "corrections_json": str(corrections_path),
        "hidden_points": corrections["hidden_points"],
    }


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    queue = service.register_listener()
    try:
        while True:
            record = await queue.get()
            await websocket.send_json(record)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        service.unregister_listener(queue)
