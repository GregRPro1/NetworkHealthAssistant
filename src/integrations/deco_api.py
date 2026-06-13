# src/integrations/deco_api.py
# Best-effort local integration for TP-Link Deco (e.g., M9/AC2200).
# Tries multiple local endpoints and normalizes connected client lists.
#
# Returns: List[dict] with keys:
#   mac, ip, hostname, vendor, ssid, vlan_id, ap_mac, band, rssi
#
# Config expected in config.yaml:
# integrations:
#   deco:
#     enabled: true
#     host: 192.168.1.1     # or a specific node's IP
#     username: "admin"     # if required
#     password: "********"  # if required
#     timeout: 2.0

from __future__ import annotations
import json
import ssl
import base64
import http.client
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from ..nha.logger import get_logger
from .deco_config import known_nodes_from_config, normalize_mac

log = get_logger("deco.api")

# ---- tiny HTTP helpers (stdlib only) ----------------------------------------

def _http_request(method: str, url: str, headers: Dict[str, str] | None = None,
                  body: bytes | None = None, timeout: float = 2.0,
                  verify_ssl: bool = False) -> Tuple[int, Dict[str, str], bytes]:
    """
    Minimal HTTP(S) request. Returns (status, headers_lower, body_bytes).
    """
    headers = headers or {}
    u = urlparse(url)
    port = u.port or (443 if u.scheme == "https" else 80)
    conn: http.client.HTTPConnection | http.client.HTTPSConnection
    if u.scheme == "https":
        ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
        conn = http.client.HTTPSConnection(u.hostname, port, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(u.hostname, port, timeout=timeout)

    path = u.path or "/"
    if u.query:
        path += f"?{u.query}"

    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, hdrs, raw
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _http_json(method: str, url: str, headers: Dict[str, str] | None = None,
               body_json: Any | None = None, timeout: float = 2.0,
               verify_ssl: bool = False) -> Tuple[int, Dict[str, str], Any]:
    """
    Sends/receives JSON; returns (status, headers, obj_or_None).
    """
    b = None
    headers = dict(headers or {})
    if body_json is not None:
        b = json.dumps(body_json).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    status, hdrs, raw = _http_request(
        method, url, headers=headers, body=b, timeout=timeout, verify_ssl=verify_ssl
    )
    obj = None
    if raw:
        try:
            obj = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            obj = None
    return status, hdrs, obj

# ---- normalizers -------------------------------------------------------------

def _norm_client(mac: str = "", ip: str = "", hostname: str = "", vendor: str = "",
                 ssid: str = "", vlan_id: int | None = None, ap_mac: str = "",
                 band: str = "", rssi: int | None = None) -> Dict[str, Any]:
    return {
        "mac": normalize_mac(mac),
        "ip": ip,
        "hostname": hostname,
        "vendor": vendor,
        "ssid": ssid,
        "vlan_id": vlan_id,
        "ap_mac": normalize_mac(ap_mac),
        "band": band,       # "2.4G" / "5G" / "6G" if provided
        "rssi": rssi
    }

def _safe_get(d: Dict[str, Any], *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict): return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _first(d: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in d and d.get(key) not in (None, ""):
            return d.get(key)
    return default


def _device_list_from_obj(obj: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    paths = [
        ("result",),
        ("result", "devices"),
        ("result", "clients"),
        ("result", "client_list"),
        ("data",),
        ("data", "devices"),
        ("data", "clients"),
        ("data", "client_list"),
        ("devices",),
        ("clients",),
        ("client_list",),
        ("wlanClientList",),
        ("wlan_client_list",),
    ]
    for path in paths:
        value: Any = obj
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return None


def _clients_from_devices(devs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d in devs:
        out.append(_norm_client(
            mac=str(_first(d, "mac", "macaddr", "macAddress", "clientMac", "client_mac")),
            ip=str(_first(d, "ip", "ipaddr", "ipAddress", "clientIp", "client_ip")),
            hostname=str(_first(d, "name", "hostname", "hostName", "deviceName", "clientName")),
            vendor=str(_first(d, "vendor", "vendorName", "manufacturer")),
            ssid=str(_first(d, "ssid", "wirelessName")),
            vlan_id=_coerce_int(_first(d, "vlan_id", "vlanId", default=None)),
            ap_mac=str(_first(d, "ap_mac", "apMac", "apMAC", "bssid", "connected_ap_mac")),
            band=str(_first(d, "band", "wirelessBand", "radio")),
            rssi=_coerce_int(_first(d, "rssi", "signal", "signalLevel", default=None)),
        ))
    return out


def _clients_from_response(obj: Any) -> Optional[List[Dict[str, Any]]]:
    if isinstance(obj, list):
        return _clients_from_devices([item for item in obj if isinstance(item, dict)])
    if isinstance(obj, dict):
        devs = _device_list_from_obj(obj)
        if isinstance(devs, list):
            return _clients_from_devices(devs)
    return None


def _base_urls_for_host(host: str) -> List[str]:
    host = (host or "").strip().rstrip("/")
    if not host:
        return []
    parsed = urlparse(host)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return [host]
    return [f"http://{host}", f"https://{host}"]


def _candidate_base_urls(cfg: Dict[str, Any]) -> List[str]:
    hosts: List[str] = []
    for value in (cfg.get("host"), cfg.get("hosts")):
        if isinstance(value, list):
            hosts.extend(str(v) for v in value if v)
        elif value:
            hosts.append(str(value))
    for node in known_nodes_from_config({"integrations": {"deco": cfg}}).values():
        if node.get("ip"):
            hosts.append(node["ip"])

    base_urls: List[str] = []
    for host in hosts or ["192.168.1.1"]:
        for base_url in _base_urls_for_host(host):
            if base_url not in base_urls:
                base_urls.append(base_url)
    return base_urls

# ---- Strategy A: Known JSON endpoints (no auth or basic auth) ---------------

def _try_getconn_devices(base_url: str, timeout: float, verify_ssl: bool) -> Optional[List[Dict[str, Any]]]:
    """
    Some Deco firmwares expose a simple client list at /api/system/getConnDevices (GET).
    May be auth-free on LAN or require basic auth.
    """
    url = f"{base_url}/api/system/getConnDevices"
    status, hdrs, obj = _http_json("GET", url, timeout=timeout, verify_ssl=verify_ssl)
    if status == 200:
        # Known shapes:
        # { "error_code":0, "result": { "devices":[ { "mac":"", "ip":"", "name":"", "vendor":"", "ssid":"", ... }, ...]}}
        # or: { "devices":[ ... ] }
        clients = _clients_from_response(obj)
        if clients is not None:
            return clients
    return None

# ---- Strategy B: LuCI-like token flow (stok) --------------------------------

def _try_luci_login(base_url: str, username: str, password: str, timeout: float,
                    verify_ssl: bool) -> Optional[str]:
    """
    Some TP-Link firmwares expose a LuCI-like login that returns a 'stok' token.
    Endpoints vary; we try a couple patterns.
    """
    # Pattern 1: /cgi-bin/luci/api/auth
    url1 = f"{base_url}/cgi-bin/luci/api/auth"
    body1 = {"method": "login", "params": {"username": username, "password": password}}
    status, hdrs, obj = _http_json("POST", url1, body_json=body1, timeout=timeout, verify_ssl=verify_ssl)
    if status == 200 and isinstance(obj, dict):
        tok = obj.get("stok") or _safe_get(obj, "data", "stok")
        if isinstance(tok, str) and tok:
            return tok

    # Pattern 2: /cgi-bin/luci/;stok=/login?form=login (fallback – sometimes basic auth)
    # If basic auth only, we can't get stok; we’ll try Basic later.
    return None

def _try_luci_clients(base_url: str, stok: str, timeout: float,
                      verify_ssl: bool) -> Optional[List[Dict[str, Any]]]:
    """
    With a stok token, try common client list locations.
    """
    paths = [
        f"{base_url}/cgi-bin/luci/;stok={stok}/api/misystem/devicelist",
        f"{base_url}/cgi-bin/luci/;stok={stok}/api/system/getConnDevices",
        f"{base_url}/cgi-bin/luci/;stok={stok}/api/misystem/connected_devices"
    ]
    for url in paths:
        status, hdrs, obj = _http_json("GET", url, timeout=timeout, verify_ssl=verify_ssl)
        if status == 200:
            clients = _clients_from_response(obj)
            if clients is not None:
                return clients
    return None

# ---- Strategy C: Basic-auth protected JSON ----------------------------------

def _try_basic_auth_clients(base_url: str, username: str, password: str, timeout: float,
                            verify_ssl: bool) -> Optional[List[Dict[str, Any]]]:
    url = f"{base_url}/api/system/getConnDevices"
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {token}"}
    status, hdrs, obj = _http_json("GET", url, headers=headers, timeout=timeout, verify_ssl=verify_ssl)
    if status == 200:
        clients = _clients_from_response(obj)
        if clients is not None:
            return clients
    return None

# ---- utilities ---------------------------------------------------------------

def _coerce_int(v) -> Optional[int]:
    try:
        if v is None or v == "": return None
        return int(v)
    except Exception:
        return None

# ---- Public API --------------------------------------------------------------

def fetch_clients(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Try multiple local methods; return normalized client list.
    """
    if not cfg or not cfg.get("enabled"):
        log.info("Deco integration disabled in config.")
        return []

    username = cfg.get("username") or ""
    password = cfg.get("password") or ""
    timeout = float(cfg.get("timeout") or 2.0)
    verify_ssl = bool(cfg.get("verify_ssl", False))
    base_urls = _candidate_base_urls(cfg)

    log.info("Deco: probing %d local base URL(s)", len(base_urls))

    for base_url in base_urls:
        log.info("Deco: probing %s", base_url)
        # Strategy A: anonymous JSON endpoint
        try:
            clients = _try_getconn_devices(base_url, timeout, verify_ssl)
            if clients:
                log.info("Deco: getConnDevices returned %d clients from %s", len(clients), base_url)
                return clients
        except Exception as e:
            log.warning("Deco: getConnDevices probe failed for %s: %s", base_url, e)

        # Strategy B/C: authenticated variants
        if username and password:
            try:
                stok = _try_luci_login(base_url, username, password, timeout, verify_ssl)
                if stok:
                    log.info("Deco: obtained stok from %s", base_url)
                    clients = _try_luci_clients(base_url, stok, timeout, verify_ssl)
                    if clients:
                        log.info("Deco: luci devicelist returned %d clients from %s", len(clients), base_url)
                        return clients
            except Exception as e:
                log.warning("Deco: luci flow failed for %s: %s", base_url, e)

            try:
                clients = _try_basic_auth_clients(base_url, username, password, timeout, verify_ssl)
                if clients:
                    log.info("Deco: basic-auth getConnDevices returned %d clients from %s", len(clients), base_url)
                    return clients
            except Exception as e:
                log.warning("Deco: basic-auth flow failed for %s: %s", base_url, e)

    log.info("Deco: no local API matched; returning empty client list")
    return []
