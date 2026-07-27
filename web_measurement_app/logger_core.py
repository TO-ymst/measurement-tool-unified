from __future__ import annotations

import csv
import datetime as dt
import io
import math
import os
import platform
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

IS_WINDOWS = os.name == "nt" or platform.system() == "Windows"

CHANNEL_FILTER: Dict[str, Dict[str, int]] = {
    "2.4GHz": {"min": 1, "max": 11},
    "5GHz": {"min": 36, "max": 165},
    "6GHz": {"min": 166, "max": 233},
}

HEADERS = [
    "Index",
    "Point",
    "Date",
    "Time",
    "SSID",
    "BSSID",
    "Channel",
    "Rate",
    "SignalStrength",
    "dBm",
    "icmp_seq",
    "ttl",
    "time_ms",
    "Status",
    "neighbor_scan_ran",
    "neighbor_match_ssid",
    "neighbor_count_visible",
    "neighbor_count_same_ssid",
    "neighbor_bssid_list",
    "best_neighbor_ssid",
    "best_neighbor_bssid",
    "best_neighbor_channel",
    "best_neighbor_rate",
    "best_neighbor_signal",
    "best_neighbor_dbm",
    "best_neighbor_signal_gap",
    "ArpTargetState",
    "PingTarget",
    "PingTargetSource",
    "Host",
    "SshStatus",
    "Error",
]

NEIGHBOR_HEADERS = [
    "Index",
    "Point",
    "Date",
    "Time",
    "Host",
    "ScanIndex",
    "SSID",
    "BSSID",
    "Channel",
    "Rate",
    "SignalStrength",
    "dBm",
]

CONNECTION_EVENT_HEADERS = [
    "Timestamp",
    "Event",
    "RequestedSSID",
    "RequestedBSSID",
    "ConnectedSSID",
    "ConnectedBSSID",
    "Channel",
    "DurationMs",
    "Result",
    "Details",
]

ADVANCED_EVENT_BSSID_CHANGED = "bssid_changed"
ADVANCED_EVENT_PING_TIMEOUT = "ping_timeout"
ADVANCED_EVENT_SSH_FAILED = "ssh_failed"

DEFAULT_MEASUREMENT_MODE = "local"
DEFAULT_SSID = "TO-Dev-WAI"
DEFAULT_BAND = "5GHz"
DEFAULT_LOG_BASE = "rec_wifi_logs"
DEFAULT_TIMEZONE = "Asia/Tokyo"
DEFAULT_USE_GATEWAY = True
DEFAULT_PING_TARGET = "192.168.30.1"
DEFAULT_INTERVAL = 1.0
DEFAULT_PING_FAIL_VALUE = 999.0
DEFAULT_PING_TIMEOUT_MS = 2000
DEFAULT_WIFI_DISCONNECTED_VALUE = 999.0
DEFAULT_USE_SUDO = not IS_WINDOWS
DEFAULT_REMOTE_USER = "nvidia"
DEFAULT_REMOTE_PORT = 22
DEFAULT_REMOTE_NEIGHBOR_EVERY = 5
DEFAULT_REMOTE_SSH_TIMEOUT_SEC = 5


def _base_remote(port: int, identity_file: str | None) -> List[str]:
    cmd = [
        "-p",
        str(port),
        "-o",
        f"ConnectTimeout={DEFAULT_REMOTE_SSH_TIMEOUT_SEC}",
        "-o",
        "ServerAliveInterval=2",
        "-o",
        "ServerAliveCountMax=2",
    ]
    if identity_file:
        cmd.extend(["-i", identity_file])
    return cmd


def _build_target(user: str, host: str) -> str:
    return f"{user}@{host}" if user else host


def _default_identity_file() -> Path:
    return Path.home() / ".ssh" / "id_ed25519"


def _build_wifi_probe_script(ping_target: str | None) -> str:
    target_expr = (
        shlex.quote(ping_target)
        if ping_target
        else '$(ip route show default 2>/dev/null | sed -n "s/^default via \\([^ ]*\\).*/\\1/p" | head -n 1)'
    )
    return f"""
WIFI_LINE="$(nmcli -t -f ACTIVE,SSID,BSSID,CHAN,RATE,SIGNAL dev wifi 2>/dev/null | grep '^yes:' | head -n 1)"
TARGET={target_expr}
PING_MS=""
PING_STATUS="skipped"
ARP_STATE=""
if [ -n "$TARGET" ]; then
  ARP_LINE="$(ip neigh show to "$TARGET" 2>/dev/null | head -n 1)"
  if [ -z "$ARP_LINE" ]; then
    ARP_LINE="$(ip neigh get "$TARGET" 2>/dev/null | head -n 1)"
  fi
  if [ -n "$ARP_LINE" ]; then
    ARP_STATE="$(printf '%s' "$ARP_LINE" | awk '{{print $NF}}')"
  else
    ARP_STATE="MISSING"
  fi
fi
if [ -n "$TARGET" ]; then
  PING_OUT="$(ping -c 1 -W 1 "$TARGET" 2>/dev/null)"
  if printf '%s' "$PING_OUT" | grep -q 'time='; then
    PING_MS="$(printf '%s' "$PING_OUT" | sed -n 's/.*time=\\([0-9.]*\\).*/\\1/p' | head -n 1)"
    PING_STATUS="ok"
  else
    PING_STATUS="timeout"
  fi
fi
printf 'WIFI=%s\\n' "$WIFI_LINE"
printf 'PING_TARGET=%s\\n' "$TARGET"
printf 'PING_MS=%s\\n' "$PING_MS"
printf 'PING_STATUS=%s\\n' "$PING_STATUS"
printf 'ARP_TARGET_STATE=%s\\n' "$ARP_STATE"
""".strip()


def _build_neighbor_scan_script(target_ssid: str | None) -> str:
    ssid_filter = shlex.quote(target_ssid or "")
    return f"""
TARGET_SSID={ssid_filter}
nmcli -t -f SSID,BSSID,CHAN,RATE,SIGNAL dev wifi list 2>/dev/null | while IFS= read -r line; do
  [ -z "$line" ] && continue
  if [ -n "$TARGET_SSID" ]; then
    case "$line" in
      "$TARGET_SSID":*) ;;
      *) continue ;;
    esac
  fi
  printf 'NEIGHBOR=%s\\n' "$line"
done
""".strip()


def _parse_key_values(stdout: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _parse_keyed_lines(stdout: str, prefix: str) -> List[str]:
    values: List[str] = []
    for line in stdout.splitlines():
        if line.startswith(prefix):
            values.append(line[len(prefix) :].strip())
    return values


def _parse_wifi_line(wifi_line: str) -> Dict[str, str]:
    row = {"ssid": "", "bssid": "", "channel": "", "rate": "", "signal": ""}
    if not wifi_line:
        return row
    reader = csv.reader([wifi_line], delimiter=":", escapechar="\\")
    fields = next(reader, [])
    if len(fields) >= 6:
        row["ssid"] = fields[1].strip()
        row["bssid"] = fields[2].strip()
        row["channel"] = fields[3].strip()
        row["rate"] = fields[4].strip()
        row["signal"] = fields[5].strip()
    return row


def _parse_neighbor_line(raw_line: str) -> Dict[str, str]:
    row = {"ssid": "", "bssid": "", "channel": "", "rate": "", "signal": ""}
    if not raw_line:
        return row
    reader = csv.reader([raw_line], delimiter=":", escapechar="\\")
    fields = next(reader, [])
    if len(fields) >= 5:
        row["ssid"] = fields[0].strip()
        row["bssid"] = fields[1].strip()
        row["channel"] = fields[2].strip()
        row["rate"] = fields[3].strip()
        row["signal"] = fields[4].strip()
    return row


def _dbm_from_signal_text(signal: str) -> str:
    if not signal:
        return ""
    try:
        return f"{(int(signal) / 2) - 100:.1f}"
    except ValueError:
        return ""


def _signal_to_int(signal: str) -> Optional[int]:
    try:
        return int(signal)
    except (TypeError, ValueError):
        return None


def _select_best_neighbor(
    neighbors: List[Dict[str, str]],
    current_ssid: str,
    current_bssid: str,
    requested_ssid: Optional[str],
) -> Optional[Dict[str, str]]:
    target_ssid = (requested_ssid or current_ssid or "").strip()
    candidates: List[Dict[str, str]] = []
    for neighbor in neighbors:
        if not neighbor.get("bssid"):
            continue
        if current_bssid and neighbor["bssid"] == current_bssid:
            continue
        if target_ssid and neighbor.get("ssid", "").strip() != target_ssid:
            continue
        if _signal_to_int(neighbor.get("signal", "")) is None:
            continue
        candidates.append(neighbor)
    if not candidates:
        return None
    candidates.sort(key=lambda item: _signal_to_int(item.get("signal", "")) or -999, reverse=True)
    return candidates[0]


def prepare_log_file(prefix: str, base_name: str, output_dir: str) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_prefix = prefix or ""
    if safe_prefix and not safe_prefix.endswith("_"):
        safe_prefix += "_"
    os.makedirs(output_dir, exist_ok=True)
    candidate = Path(output_dir) / f"{safe_prefix}{base_name}_{timestamp}.csv"
    counter = 1
    while candidate.exists():
        candidate = Path(output_dir) / f"{safe_prefix}{base_name}_{timestamp}_{counter}.csv"
        counter += 1
    return candidate


def prepare_neighbor_log_file(log_path: Path) -> Path:
    return log_path.with_name(f"{log_path.stem}_neighbors{log_path.suffix}")


def prepare_connection_event_file(log_path: Path) -> Path:
    return log_path.with_name(f"{log_path.stem}_events{log_path.suffix}")


def should_run_neighbor_scan(sample_index: int, every: int) -> bool:
    return every > 0 and sample_index > 0 and (sample_index - 1) % every == 0


def apply_neighbor_summary(
    row: Dict[str, object],
    neighbors: List[Dict[str, str]],
    requested_ssid: Optional[str],
) -> None:
    row.update(
        {
            "neighbor_scan_ran": "yes",
            "neighbor_match_ssid": "",
            "neighbor_count_visible": str(len(neighbors)),
            "neighbor_count_same_ssid": "",
            "neighbor_bssid_list": "",
            "best_neighbor_ssid": "",
            "best_neighbor_bssid": "",
            "best_neighbor_channel": "",
            "best_neighbor_rate": "",
            "best_neighbor_signal": "",
            "best_neighbor_dbm": "",
            "best_neighbor_signal_gap": "",
        }
    )
    current_ssid = str(row.get("ssid", ""))
    current_bssid = str(row.get("bssid", ""))
    target_ssid = (requested_ssid or current_ssid).strip()
    row["neighbor_match_ssid"] = target_ssid
    same_ssid_neighbors = (
        [
            item
            for item in neighbors
            if item.get("ssid", "").strip() == target_ssid and item.get("bssid") != current_bssid
        ]
        if target_ssid
        else []
    )
    row["neighbor_count_same_ssid"] = str(len(same_ssid_neighbors))
    row["neighbor_bssid_list"] = "|".join(item["bssid"] for item in same_ssid_neighbors if item.get("bssid"))
    best_neighbor = _select_best_neighbor(neighbors, current_ssid, current_bssid, requested_ssid)
    if not best_neighbor:
        return
    row["best_neighbor_ssid"] = best_neighbor["ssid"]
    row["best_neighbor_bssid"] = best_neighbor["bssid"]
    row["best_neighbor_channel"] = best_neighbor["channel"]
    row["best_neighbor_rate"] = best_neighbor["rate"]
    row["best_neighbor_signal"] = best_neighbor["signal"]
    row["best_neighbor_dbm"] = _dbm_from_signal_text(best_neighbor["signal"])
    current_signal = _signal_to_int(str(row.get("signal", "")))
    best_signal = _signal_to_int(best_neighbor["signal"])
    if current_signal is not None and best_signal is not None:
        row["best_neighbor_signal_gap"] = str(best_signal - current_signal)


def prepare_sidecar_file(prefix: str, base_name: str, output_dir: str, suffix: str) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_prefix = prefix or ""
    if safe_prefix and not safe_prefix.endswith("_"):
        safe_prefix += "_"
    os.makedirs(output_dir, exist_ok=True)
    candidate = Path(output_dir) / f"{safe_prefix}{base_name}_{timestamp}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = Path(output_dir) / f"{safe_prefix}{base_name}_{timestamp}_{counter}{suffix}"
        counter += 1
    return candidate


def detect_default_gateway() -> Optional[str]:
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$routes = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | "
                    "Sort-Object -Property RouteMetric; "
                    "$wifi = $routes | Where-Object { $_.InterfaceAlias -match 'Wi-Fi' -or $_.InterfaceDescription -match 'Wi-Fi' } | Select-Object -First 1; "
                    "if ($wifi) { $wifi.NextHop } else { ($routes | Select-Object -First 1).NextHop }",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=True,
            )
            gateway = (result.stdout or "").strip()
            if gateway:
                return gateway
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    commands = (
        ["ip", "route", "show", "default"],
        ["ip", "route"],
        ["route", "-n"],
    )
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("default"):
                parts = stripped.split()
                if "via" in parts:
                    via_idx = parts.index("via")
                    if via_idx + 1 < len(parts):
                        return parts[via_idx + 1]
            if cmd[0] == "route" and stripped.startswith("0.0.0.0"):
                parts = stripped.split()
                if len(parts) >= 2:
                    return parts[1]
    return None


def build_nmcli_command(use_sudo: bool) -> List[str]:
    cmd = [
        "nmcli",
        "--terse",
        "--fields",
        "ACTIVE,SSID,BSSID,CHAN,RATE,SIGNAL",
        "dev",
        "wifi",
    ]
    if use_sudo:
        cmd.insert(0, "sudo")
    return cmd


def get_wifi_output(use_sudo: bool) -> str:
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("netsh 繧ｳ繝槭Φ繝峨′隕九▽縺九ｊ縺ｾ縺帙ｓ (Wi-Fi諠・ｱ蜿門ｾ励↓蠢・ｦ・") from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or "").strip() or "netsh 縺ｮ螳溯｡後↓螟ｱ謨励＠縺ｾ縺励◆"
            raise RuntimeError(message) from exc
        return result.stdout or ""

    cmd = build_nmcli_command(use_sudo)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("nmcli 繧ｳ繝槭Φ繝峨′隕九▽縺九ｊ縺ｾ縺帙ｓ") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or "nmcli 縺ｮ螳溯｡後↓螟ｱ謨励＠縺ｾ縺励◆"
        raise RuntimeError(message) from exc
    return result.stdout


def parse_wifi_info(
    output: str,
    target_ssid: str,
    min_channel: int,
    max_channel: int,
) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    reader = csv.reader(io.StringIO(output), delimiter=":", escapechar="\\")
    for row in reader:
        if len(row) < 6:
            continue
        active_flag, ssid, bssid, chan_str, rate, signal_str = row[:6]
        if active_flag != "yes":
            continue
        if target_ssid and ssid != target_ssid:
            continue
        try:
            channel = int(chan_str)
            signal = int(signal_str)
        except ValueError:
            continue
        if not (min_channel <= channel <= max_channel):
            continue
        dbm = (signal / 2) - 100
        matches.append(
            {
                "ssid": ssid,
                "bssid": bssid,
                "channel": channel,
                "rate": rate.replace(" Mbit/s", "Mbit/s"),
                "signal": signal,
                "dbm": dbm,
            }
        )
    return matches


def list_available_ssids(use_sudo: bool) -> List[str]:
    ssids: List[str] = []
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=True,
            )
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("SSID ") and ":" in line:
                    # SSID 1 : MyWiFi
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        name = parts[1].strip()
                        if name and name not in ssids:
                            ssids.append(name)
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        return ssids

    # Linux (nmcli)
    cmd = ["nmcli", "-t", "-f", "SSID", "dev", "wifi"]
    if use_sudo:
        cmd.insert(0, "sudo")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            name = line.strip()
            if name and name not in ssids:
                ssids.append(name)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return ssids


def parse_netsh_wifi_info(
    output: str, target_ssid: str, min_channel: int, max_channel: int
) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    current: Dict[str, object] = {}

    def maybe_store() -> None:
        nonlocal current
        ssid = current.get("ssid")
        channel = current.get("channel")
        signal = current.get("signal")
        if not ssid or channel is None or signal is None:
            current = {}
            return
        if target_ssid and ssid != target_ssid:
            current = {}
            return
        if not (min_channel <= int(channel) <= max_channel):
            current = {}
            return
        rate = current.get("rate", "")
        dbm = (int(signal) / 2) - 100
        matches.append(
            {
                "ssid": ssid,
                "bssid": str(current.get("bssid", "")),
                "channel": int(channel),
                "rate": rate,
                "signal": int(signal),
                "dbm": dbm,
            }
        )
        current = {}

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            maybe_store()
            continue

        if line.startswith("SSID") and ":" in line:
            maybe_store()
            parts = line.split(":", 1)
            ssid_val = parts[1].strip()
            if ssid_val and not ssid_val.isdigit():
                current["ssid"] = ssid_val
            continue

        if not current:
            continue

        if (line.lower().startswith("bssid") or line.lower().startswith("ap bssid")) and ":" in line:
            current["bssid"] = line.split(":", 1)[1].strip()
            continue

        if ":" not in line:
            continue
        key_raw, value_raw = line.split(":", 1)
        key = key_raw.strip().lower()
        value = value_raw.strip()

        if key in ("state", "状態"):
            state_val = value.lower()
            if not ("connected" in state_val or "接続" in state_val):
                current = {}
            continue

        if key in ("channel", "チャネル"):
            try:
                current["channel"] = int(value)
            except ValueError:
                pass
            continue

        if key in ("receive rate (mbps)", "transmit rate (mbps)", "受信速度", "送信速度"):
            rate_val = value
            number_match = re.search(r"(\d+)", rate_val)
            if number_match:
                rate_number = number_match.group(1)
                existing_rate = current.get("rate", "")
                if existing_rate:
                    try:
                        existing_number = int(re.search(r"(\d+)", str(existing_rate)).group(1))
                    except Exception:
                        existing_number = 0
                    current["rate"] = f"{max(existing_number, int(rate_number))}Mbit/s"
                else:
                    current["rate"] = f"{rate_number}Mbit/s"
            continue

        if key in ("signal", "シグナル"):
            percent_match = re.search(r"(\d+)", line)
            if percent_match:
                current["signal"] = int(percent_match.group(1))
            continue

    maybe_store()
    return matches


def fetch_wifi_rows(
    use_sudo: bool,
    target_ssid: str,
    min_channel: int,
    max_channel: int,
) -> List[Dict[str, object]]:
    if IS_WINDOWS:
        output = get_wifi_output(use_sudo=False)
        return parse_netsh_wifi_info(output, target_ssid, min_channel, max_channel)

    wifi_output = get_wifi_output(use_sudo)
    return parse_wifi_info(wifi_output, target_ssid, min_channel, max_channel)


def _parse_netsh_neighbor_rows(output: str, target_ssid: Optional[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    current_ssid = ""
    current: Optional[Dict[str, str]] = None

    def store_current() -> None:
        nonlocal current
        if current and current.get("bssid") and (not target_ssid or current.get("ssid", "").strip() == target_ssid):
            rows.append(current)
        current = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", line, re.IGNORECASE)
        if ssid_match:
            store_current()
            current_ssid = ssid_match.group(1).strip()
            continue
        bssid_match = re.match(r"^BSSID\s+\d+\s*:\s*(.*)$", line, re.IGNORECASE)
        if bssid_match:
            store_current()
            current = {"ssid": current_ssid, "bssid": bssid_match.group(1).strip(), "channel": "", "rate": "", "signal": ""}
            continue
        if not current:
            continue
        signal_match = re.match(r"^(?:Signal|\u30b7\u30b0\u30ca\u30eb)\s*:\s*(\d+)", line, re.IGNORECASE)
        if signal_match:
            current["signal"] = signal_match.group(1)
            continue
        channel_match = re.match(r"^(?:Channel|\u30c1\u30e3\u30cd\u30eb)\s*:\s*(\d+)", line, re.IGNORECASE)
        if channel_match:
            current["channel"] = channel_match.group(1)
    store_current()
    return rows


def scan_local_neighbors(use_sudo: bool, target_ssid: Optional[str]) -> List[Dict[str, str]]:
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=Bssid"],
                capture_output=True,
                text=True,
                encoding="cp932",
                errors="ignore",
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("netsh neighbor scan failed") from exc
        return _parse_netsh_neighbor_rows(result.stdout or "", target_ssid)

    cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,RATE,SIGNAL", "dev", "wifi", "list"]
    if use_sudo:
        cmd.insert(0, "sudo")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("nmcli command was not found") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or "nmcli neighbor scan failed") from exc
    neighbors = [_parse_neighbor_line(line) for line in result.stdout.splitlines()]
    return [
        row
        for row in neighbors
        if row.get("bssid") and (not target_ssid or row.get("ssid", "").strip() == target_ssid)
    ]


def get_current_local_wifi_state(use_sudo: bool) -> Dict[str, object]:
    rows = fetch_wifi_rows(use_sudo, "", 1, 233)
    return rows[0] if rows else {}


def switch_local_wifi_bssid(use_sudo: bool, ssid: str, bssid: str) -> Dict[str, object]:
    if IS_WINDOWS:
        raise RuntimeError("BSSID switching is supported on Jetson/Linux only")
    normalized_ssid = ssid.strip()
    normalized_bssid = bssid.strip().lower()
    if not normalized_ssid:
        raise RuntimeError("SSID is required")
    if not re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", normalized_bssid):
        raise RuntimeError("Invalid BSSID format")

    cmd = ["nmcli", "--wait", "30", "device", "wifi", "connect", normalized_ssid, "bssid", normalized_bssid]
    if use_sudo:
        cmd.insert(0, "sudo")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=35)
    except FileNotFoundError as exc:
        raise RuntimeError("nmcli command was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("BSSID switch timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "nmcli connection failed").strip()
        raise RuntimeError(detail)

    connected = get_current_local_wifi_state(use_sudo)
    actual_bssid = str(connected.get("bssid", "")).lower()
    if actual_bssid != normalized_bssid:
        raise RuntimeError(f"Connected BSSID verification failed: {actual_bssid or 'not connected'}")
    return connected


def get_ping_result(
    target_ip: str,
    timeout_as_numeric: bool,
    fail_value: float,
    ping_timeout_ms: int,
) -> Tuple[str, str, str, str]:
    timeout_ms = max(1, int(ping_timeout_ms))
    if IS_WINDOWS:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), target_ip]
    else:
        timeout_sec = max(1, math.ceil(timeout_ms / 1000))
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec), target_ip]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="cp932" if IS_WINDOWS else "utf-8",
            errors="ignore",
            check=True,
        )
        stdout = result.stdout
    except FileNotFoundError:
        return ("", "", "NaN", "ping_command_not_found")
    except subprocess.CalledProcessError as exc:
        stdout = (exc.stdout or "").decode("cp932", "ignore") if isinstance(exc.stdout, (bytes, bytearray)) else (exc.stdout or "")

    icmp_seq = None
    ttl = None
    time_ms = None

    for line in stdout.splitlines():
        lowered = line.lower()
        if IS_WINDOWS:
            time_match = re.search(r"(?:time|時間)\s*[=<]?\s*([0-9]+)\s*ms", line, re.IGNORECASE)
            ttl_match = re.search(r"ttl[\s:=]*([0-9]+)", line, re.IGNORECASE)
            if time_match:
                time_ms = time_match.group(1)
            if ttl_match:
                ttl = ttl_match.group(1)
            if time_ms is not None:
                icmp_seq = icmp_seq or "1"
                break
            if ("request timed out" in lowered) or ("timed out" in lowered) or ("タイムアウト" in line):
                icmp_seq = icmp_seq or "timeout"
                ttl = ttl or "timeout"
        else:
            if "icmp_seq" not in line:
                continue
            parts = line.split()
            for part in parts:
                if part.startswith("icmp_seq="):
                    icmp_seq = part.split("=", 1)[1]
                elif part.startswith("ttl="):
                    ttl = part.split("=", 1)[1]
                elif part.startswith("time="):
                    time_ms = part.split("=", 1)[1].replace(" ms", "")
    if time_ms is None:
        icmp_seq = icmp_seq or "timeout"
        ttl = ttl or "timeout"
        time_ms = str(fail_value) if timeout_as_numeric else "NaN"
        status = "ping_timeout"
    else:
        status = "ok"
    return icmp_seq or "", ttl or "", time_ms, status


def resolve_ping_target(
    ping_target: Optional[str],
    auto_gateway: bool,
    fallback: str = DEFAULT_PING_TARGET,
) -> Tuple[str, str]:
    if ping_target:
        return ping_target, "manual"
    if auto_gateway:
        gateway = detect_default_gateway()
        if gateway:
            return gateway, "gateway"
        return fallback, "gateway_fallback"
    return fallback, "default"


def get_current_ssid(use_sudo: bool) -> Optional[str]:
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        ssid_match = re.search(r"SSID\s*:\s*(.+)", result.stdout or "")
        if ssid_match:
            ssid = ssid_match.group(1).strip()
            return ssid or None
        return None

    cmd = ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"]
    if use_sudo:
        cmd.insert(0, "sudo")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    for line in result.stdout.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[0] == "yes":
            return parts[1]
    return None


def ensure_remote_ssh_key(
    host: str,
    user: str,
    port: int,
    identity_file: Optional[str],
    comment: Optional[str],
) -> str:
    identity_path = Path(identity_file).expanduser() if identity_file else _default_identity_file()
    public_key_path = (
        identity_path.with_suffix(identity_path.suffix + ".pub")
        if identity_path.suffix
        else Path(f"{identity_path}.pub")
    )
    identity_path.parent.mkdir(parents=True, exist_ok=True)

    if not identity_path.exists():
        keygen_cmd = ["ssh-keygen", "-t", "ed25519", "-f", str(identity_path), "-N", ""]
        if comment:
            keygen_cmd.extend(["-C", comment])
        subprocess.run(keygen_cmd, text=True, check=True, timeout=30)

    public_key = public_key_path.read_text(encoding="utf-8").strip()
    quoted_key = shlex.quote(public_key)
    remote_script = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        f"grep -qxF {quoted_key} ~/.ssh/authorized_keys 2>/dev/null || "
        f"printf '%s\\n' {quoted_key} >> ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys"
    )
    ssh_cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        *_base_remote(port, str(identity_path)),
        _build_target(user, host),
        remote_script,
    ]
    subprocess.run(ssh_cmd, text=True, check=True, timeout=15)
    return str(identity_path)


def remove_remote_ssh_key(
    host: str,
    user: str,
    port: int,
    identity_file: Optional[str],
    delete_local: bool,
) -> None:
    identity_path = Path(identity_file).expanduser() if identity_file else _default_identity_file()
    public_key_path = (
        identity_path.with_suffix(identity_path.suffix + ".pub")
        if identity_path.suffix
        else Path(f"{identity_path}.pub")
    )
    if not public_key_path.exists():
        return

    public_key = public_key_path.read_text(encoding="utf-8").strip()
    quoted_key = shlex.quote(public_key)
    remote_script = (
        "if [ -f ~/.ssh/authorized_keys ]; then "
        f"grep -vxF {quoted_key} ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.tmp || true; "
        "mv ~/.ssh/authorized_keys.tmp ~/.ssh/authorized_keys; "
        "chmod 600 ~/.ssh/authorized_keys; "
        "fi"
    )
    ssh_cmd = ["ssh", *_base_remote(port, str(identity_path)), _build_target(user, host), remote_script]
    subprocess.run(ssh_cmd, text=True, check=True, timeout=15)

    if delete_local:
        if public_key_path.exists():
            public_key_path.unlink()
        if identity_path.exists():
            identity_path.unlink()


def probe_remote_ssh(
    host: str,
    user: str,
    port: int,
    identity_file: Optional[str],
) -> str:
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        *_base_remote(port, identity_file),
        _build_target(user, host),
        "echo",
        "ssh_ok",
    ]
    result = subprocess.run(
        ssh_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=10,
    )
    return (result.stdout or "").strip()


def fetch_remote_wifi_state(
    host: str,
    user: str,
    port: int,
    identity_file: Optional[str],
    ping_target: Optional[str],
    neighbor_every: int,
    sample_index: int,
    neighbor_ssid: Optional[str],
) -> Dict[str, object]:
    target = _build_target(user, host)
    probe_script = _build_wifi_probe_script(ping_target)
    probe_cmd = ["ssh", *_base_remote(port, identity_file), target, probe_script]
    try:
        result = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {
            "ssid": "",
            "bssid": "",
            "channel": "",
            "rate": "",
            "signal": "",
            "dbm": "",
            "ping_target": "",
            "ping_ms": "",
            "ping_status": "",
            "neighbor_scan_ran": "no",
            "neighbor_match_ssid": "",
            "neighbor_count_visible": "",
            "neighbor_count_same_ssid": "",
            "neighbor_bssid_list": "",
            "best_neighbor_ssid": "",
            "best_neighbor_bssid": "",
            "best_neighbor_channel": "",
            "best_neighbor_rate": "",
            "best_neighbor_signal": "",
            "best_neighbor_dbm": "",
            "best_neighbor_signal_gap": "",
            "arp_target_state": "",
            "ssh_status": "error:timeout",
            "error": "remote_probe_timeout",
            "host": host,
            "_neighbor_rows": [],
        }

    row: Dict[str, object] = {
        "ssid": "",
        "bssid": "",
        "channel": "",
        "rate": "",
        "signal": "",
        "dbm": "",
        "ping_target": "",
        "ping_ms": "",
        "ping_status": "",
        "neighbor_scan_ran": "no",
        "neighbor_match_ssid": "",
        "neighbor_count_visible": "",
        "neighbor_count_same_ssid": "",
        "neighbor_bssid_list": "",
        "best_neighbor_ssid": "",
        "best_neighbor_bssid": "",
        "best_neighbor_channel": "",
        "best_neighbor_rate": "",
        "best_neighbor_signal": "",
        "best_neighbor_dbm": "",
        "best_neighbor_signal_gap": "",
        "arp_target_state": "",
        "ssh_status": "ok" if result.returncode == 0 else f"error:{result.returncode}",
        "error": "",
        "host": host,
        "_neighbor_rows": [],
    }

    if result.returncode == 0:
        parsed = _parse_key_values(result.stdout)
        row.update(_parse_wifi_line(parsed.get("WIFI", "")))
        row["dbm"] = _dbm_from_signal_text(str(row["signal"]))
        row["ping_target"] = parsed.get("PING_TARGET", "")
        row["ping_ms"] = parsed.get("PING_MS", "")
        row["ping_status"] = parsed.get("PING_STATUS", "")
        row["arp_target_state"] = parsed.get("ARP_TARGET_STATE", "")
        if not row["bssid"]:
            row["error"] = "no_active_wifi"
    else:
        stderr_text = (result.stderr or "").strip()
        stdout_text = (result.stdout or "").strip()
        row["error"] = stderr_text or stdout_text or "ssh_failed"

    if should_run_neighbor_scan(sample_index, neighbor_every):
        neighbor_script = _build_neighbor_scan_script(neighbor_ssid)
        neighbor_cmd = ["ssh", *_base_remote(port, identity_file), target, neighbor_script]
        try:
            neighbor_result = subprocess.run(
                neighbor_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            row["error"] = str(row["error"] or "neighbor_scan_timeout")
            return row
        if neighbor_result.returncode == 0:
            neighbor_lines = _parse_keyed_lines(neighbor_result.stdout, "NEIGHBOR=")
            parsed_neighbors: List[Dict[str, str]] = []
            for neighbor_line in neighbor_lines:
                neighbor_row = _parse_neighbor_line(neighbor_line)
                if neighbor_row["bssid"]:
                    parsed_neighbors.append(neighbor_row)
            row["_neighbor_rows"] = parsed_neighbors
            apply_neighbor_summary(row, parsed_neighbors, neighbor_ssid)
        else:
            row["error"] = str(row["error"] or "neighbor_scan_failed")

    return row


def _normalize_command_capture(
    stdout: str,
    stderr: str,
    returncode: Optional[int],
    max_chars: int,
    command: str,
) -> Dict[str, object]:
    def trim(text: str) -> str:
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...[truncated]..."

    return {
        "command": command,
        "returncode": returncode,
        "stdout": trim(stdout or ""),
        "stderr": trim(stderr or ""),
        "ok": returncode == 0,
    }


def _capture_remote_command(
    host: str,
    user: str,
    port: int,
    identity_file: Optional[str],
    command: str,
    *,
    max_chars: int,
) -> Dict[str, object]:
    ssh_cmd = ["ssh", *_base_remote(port, identity_file), _build_target(user, host), command]
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
    except FileNotFoundError as exc:
        return _normalize_command_capture("", str(exc), None, max_chars, command)
    except subprocess.TimeoutExpired:
        return _normalize_command_capture("", "remote_command_timeout", None, max_chars, command)
    return _normalize_command_capture(
        result.stdout or "",
        result.stderr or "",
        result.returncode,
        max_chars,
        command,
    )


def collect_remote_advanced_snapshot(
    *,
    host: str,
    user: str,
    port: int,
    identity_file: Optional[str],
    include_neighbor: bool,
    include_routes: bool,
    include_ip_addr: bool,
    include_wifi_details: bool,
    include_journal: bool,
    max_output_chars: int,
) -> Dict[str, object]:
    commands: Dict[str, str] = {}
    if include_neighbor:
        commands["arp_full"] = "ip neigh show"
    if include_routes:
        commands["routes"] = "ip route show"
    if include_ip_addr:
        commands["addr"] = "ip addr show"
        commands["link"] = "ip link show"
    if include_wifi_details:
        commands["wifi_link"] = "iw dev wlan0 link"
        commands["wifi_device"] = "nmcli device show wlan0"
    if include_journal:
        commands["journal"] = "journalctl -u wpa_supplicant -u NetworkManager -k --since '10 minutes ago' --no-pager"

    snapshot: Dict[str, object] = {}
    for key, command in commands.items():
        snapshot[key] = _capture_remote_command(
            host,
            user,
            port,
            identity_file,
            command,
            max_chars=max_output_chars,
        )
    return snapshot

