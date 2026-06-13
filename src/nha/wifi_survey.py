from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.integrations.deco_config import known_nodes_from_config, normalize_mac
from src.nha.net_health import iperf3_test, ping_ms, speedtest


def _run(cmd: List[str], timeout: int = 15) -> str:
    return subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _netsh_wlan(args: List[str]) -> str:
    if not platform.system().lower().startswith("win"):
        return ""
    try:
        return _run(["netsh", "wlan"] + args, timeout=15)
    except Exception:
        return ""


def _parse_percent(value: Any) -> Optional[int]:
    m = re.search(r"(\d+)", str(value or ""))
    return int(m.group(1)) if m else None


def _node_for_bssid(bssid: str, nodes: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    bssid = normalize_mac(bssid)
    for ip, node in nodes.items():
        candidates = {normalize_mac(node.get("mac"))}
        candidates.update(normalize_mac(v) for v in node.get("bssids", []) or [])
        if bssid in candidates:
            out = dict(node)
            out["ip"] = ip
            return out
    return None


def current_wifi() -> Dict[str, Any]:
    txt = _netsh_wlan(["show", "interfaces"])
    if not txt:
        return {"available": False, "raw": ""}

    key_map = {
        "name": "interface",
        "description": "adapter",
        "state": "state",
        "ssid": "ssid",
        "bssid": "bssid",
        "ap bssid": "bssid",
        "band": "band",
        "channel": "channel",
        "radio type": "radio_type",
        "receive rate (mbps)": "rx_mbps",
        "transmit rate (mbps)": "tx_mbps",
        "signal": "signal_pct",
        "rssi": "rssi_dbm",
        "profile": "profile",
    }
    row: Dict[str, Any] = {"available": True}
    for line in txt.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = re.sub(r"\s+", " ", key.strip().lower())
        value = value.strip()
        mapped = key_map.get(key)
        if not mapped:
            continue
        if mapped == "signal_pct":
            row[mapped] = _parse_percent(value)
        elif mapped == "rssi_dbm":
            try:
                row[mapped] = int(value)
            except Exception:
                row[mapped] = value
        elif mapped in ("rx_mbps", "tx_mbps"):
            try:
                row[mapped] = float(value)
            except Exception:
                row[mapped] = value
        elif mapped == "bssid":
            row[mapped] = normalize_mac(value)
        else:
            row[mapped] = value
    row["raw"] = txt
    return row


def visible_bssids() -> List[Dict[str, Any]]:
    txt = _netsh_wlan(["show", "networks", "mode=bssid"])
    if not txt:
        return []

    records: List[Dict[str, Any]] = []
    ssid = ""
    auth = ""
    encryption = ""
    current: Optional[Dict[str, Any]] = None
    for line in txt.splitlines():
        m_ssid = re.match(r"\s*SSID\s+\d+\s*:\s*(.*)$", line)
        if m_ssid:
            ssid = m_ssid.group(1).strip()
            auth = ""
            encryption = ""
            current = None
            continue
        if current is None and ":" in line:
            key, value = line.split(":", 1)
            key = re.sub(r"\s+", " ", key.strip().lower())
            value = value.strip()
            if key == "authentication":
                auth = value
            elif key == "encryption":
                encryption = value
            continue
        m_bssid = re.match(r"\s*BSSID\s+\d+\s*:\s*([0-9a-fA-F:\-]{17})", line)
        if m_bssid:
            current = {
                "ssid": ssid,
                "bssid": normalize_mac(m_bssid.group(1)),
                "authentication": auth,
                "encryption": encryption,
            }
            records.append(current)
            continue
        if current and ":" in line:
            key, value = line.split(":", 1)
            key = re.sub(r"\s+", " ", key.strip().lower())
            value = value.strip()
            if key == "signal":
                current["signal_pct"] = _parse_percent(value)
            elif key == "radio type":
                current["radio_type"] = value
            elif key == "band":
                current["band"] = value
            elif key == "channel":
                current["channel"] = value
    return records


def ping_targets(targets: List[str]) -> List[Dict[str, Any]]:
    out = []
    for target in targets:
        ms = ping_ms(target)
        out.append({"target": target, "latency_ms": ms})
    return out


def nas_file_test(path: str, size_mb: int = 16) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    size_mb = max(1, int(size_mb or 16))
    test_path = root / f"nha_speed_{socket.gethostname()}_{int(time.time())}.bin"
    chunk = os.urandom(1024 * 1024)

    try:
        t0 = time.perf_counter()
        with test_path.open("wb") as f:
            for _ in range(size_mb):
                f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
        write_s = max(0.001, time.perf_counter() - t0)

        t1 = time.perf_counter()
        with test_path.open("rb") as f:
            while f.read(1024 * 1024):
                pass
        read_s = max(0.001, time.perf_counter() - t1)
        return {
            "path": str(root),
            "size_mb": size_mb,
            "write_mbps": round((size_mb * 8) / write_s, 2),
            "read_mbps": round((size_mb * 8) / read_s, 2),
        }
    except Exception as exc:
        return {"path": str(root), "size_mb": size_mb, "error": str(exc)}
    finally:
        try:
            test_path.unlink(missing_ok=True)
        except Exception:
            pass


def _with_node_labels(records: List[Dict[str, Any]], nodes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in records:
        item = dict(row)
        node = _node_for_bssid(item.get("bssid", ""), nodes)
        if node:
            item["node_name"] = node.get("name", "")
            item["node_ip"] = node.get("ip", "")
        else:
            item["node_name"] = ""
            item["node_ip"] = ""
        out.append(item)
    return out


def roaming_findings(current: Dict[str, Any], visible: List[Dict[str, Any]]) -> List[str]:
    findings: List[str] = []
    if not current.get("available") or not current.get("ssid"):
        return ["No connected Wi-Fi interface was reported by Windows."]

    ssid = current.get("ssid")
    bssid = normalize_mac(current.get("bssid"))
    signal = current.get("signal_pct")
    band = str(current.get("band") or "")
    same_ssid = [row for row in visible if row.get("ssid") == ssid and row.get("signal_pct") is not None]
    same_ssid.sort(key=lambda row: int(row.get("signal_pct") or 0), reverse=True)

    if signal is not None and signal < 55:
        findings.append(f"Current Wi-Fi signal is weak at {signal}% on {bssid}.")

    strongest = same_ssid[0] if same_ssid else None
    if strongest and normalize_mac(strongest.get("bssid")) != bssid and signal is not None:
        delta = int(strongest.get("signal_pct") or 0) - int(signal)
        if delta >= 15:
            findings.append(
                f"Roaming concern: connected to {bssid} at {signal}%, "
                f"but {strongest.get('bssid')} is visible at {strongest.get('signal_pct')}%."
            )

    if "2.4" in band:
        five_ghz = [row for row in same_ssid if "5" in str(row.get("band", ""))]
        if five_ghz:
            best_5 = max(five_ghz, key=lambda row: int(row.get("signal_pct") or 0))
            findings.append(
                f"Connected on 2.4 GHz; strongest visible 5 GHz BSSID is "
                f"{best_5.get('bssid')} at {best_5.get('signal_pct')}%."
            )

    return findings


def run_survey(
    cfg: Dict[str, Any],
    location: str = "",
    run_internet_speed: bool = False,
    run_lan_iperf: bool = False,
    run_nas_test: bool = False,
) -> Dict[str, Any]:
    health = cfg.get("health", {}) or {}
    survey_cfg = cfg.get("wifi_survey", {}) or {}
    nodes = known_nodes_from_config(cfg)

    current = current_wifi()
    visible = _with_node_labels(visible_bssids(), nodes)
    current_node = _node_for_bssid(current.get("bssid", ""), nodes)
    if current_node:
        current["node_name"] = current_node.get("name", "")
        current["node_ip"] = current_node.get("ip", "")

    internet_hosts = health.get("internet_hosts", ["1.1.1.1", "8.8.8.8"])
    lan_targets = health.get("lan_targets", ["192.168.1.1"])
    result: Dict[str, Any] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "location": location.strip() or "",
        "wifi": {
            "current": current,
            "visible_bssids": visible,
            "findings": roaming_findings(current, visible),
        },
        "latency": {
            "internet": ping_targets(list(internet_hosts)),
            "lan": ping_targets(list(lan_targets)),
        },
        "throughput": {
            "internet_speed": None,
            "lan_iperf3": None,
            "nas_file": None,
        },
    }

    if run_internet_speed:
        st_cfg = health.get("speedtest", {}) or {}
        result["throughput"]["internet_speed"] = speedtest(st_cfg.get("binary") or "speedtest")

    if run_lan_iperf:
        ipf = health.get("iperf3", {}) or {}
        server = ipf.get("server")
        if server:
            result["throughput"]["lan_iperf3"] = iperf3_test(server)
        else:
            result["throughput"]["lan_iperf3"] = {"error": "No health.iperf3.server configured"}

    if run_nas_test:
        path = survey_cfg.get("nas_test_path") or survey_cfg.get("output_dir") or ""
        size_mb = int(survey_cfg.get("nas_test_size_mb") or 16)
        result["throughput"]["nas_file"] = nas_file_test(path, size_mb)

    return result


def save_observation(result: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, str]:
    survey_cfg = cfg.get("wifi_survey", {}) or {}
    output_dir = Path(survey_cfg.get("output_dir") or "data/wifi_surveys")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        output_dir = Path("data/wifi_surveys")
        output_dir.mkdir(parents=True, exist_ok=True)
    host = re.sub(r"[^A-Za-z0-9_.-]+", "_", result.get("host") or "host")
    stamp = re.sub(r"[^0-9A-Za-z]+", "", result.get("captured_at", ""))
    json_path = output_dir / f"wifi_survey_{host}_{stamp}.json"
    jsonl_path = output_dir / "wifi_survey_history.jsonl"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")
    return {"json": str(json_path), "jsonl": str(jsonl_path)}


def summarize(result: Dict[str, Any]) -> str:
    cur = result.get("wifi", {}).get("current", {}) or {}
    node = cur.get("node_name") or cur.get("bssid") or "unknown"
    signal = cur.get("signal_pct")
    band = cur.get("band") or "?"
    rssi = cur.get("rssi_dbm")
    rx = cur.get("rx_mbps")
    tx = cur.get("tx_mbps")
    lines = [
        f"Location: {result.get('location') or '(not set)'}",
        f"Host: {result.get('host')}  Captured: {result.get('captured_at')}",
        f"Connected: {node}  {cur.get('bssid', '')}  {signal}%  {band}  RSSI {rssi}",
        f"Wi-Fi rate: {rx} Mbps downlink / {tx} Mbps uplink",
    ]
    for item in result.get("wifi", {}).get("findings", []):
        lines.append(f"- {item}")
    return "\n".join(lines)
