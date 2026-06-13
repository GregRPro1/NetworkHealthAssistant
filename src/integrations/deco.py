# src/integrations/deco.py
from __future__ import annotations
import socket, http.client, re, time, urllib.parse
from typing import Dict, List, Tuple, Optional
from xml.etree import ElementTree as ET

# Small, dependency-free helpers to probe devices for TP-Link Deco fingerprints.

def _http_get_root(ip: str, timeout: float = 0.8) -> Tuple[Dict[str,str], str]:
    """
    GET http://<ip>/ with a short timeout. Returns (headers_lower, body[:8k]).
    """
    hdrs: Dict[str,str] = {}
    body = ""
    try:
        conn = http.client.HTTPConnection(ip, 80, timeout=timeout)
        conn.request("GET", "/", headers={"Connection": "close", "User-Agent": "NHA/1.0"})
        resp = conn.getresponse()
        for k, v in resp.getheaders():
            hdrs[k.lower()] = v
        data = resp.read(8192)  # first 8k is plenty for title probes
        body = (data or b"").decode("utf-8", errors="ignore")
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return hdrs, body


def _parse_html_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, flags=re.I|re.S)
    return (m.group(1).strip() if m else "")


def _ssdp_probe(timeout: float = 1.2) -> List[Dict[str,str]]:
    """
    Send one M-SEARCH and collect UPnP responses: returns list of header dicts (lower-cased keys).
    """
    MCAST = ("239.255.255.250", 1900)
    req = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {MCAST[0]}:{MCAST[1]}\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 1\r\n"
        "ST: ssdp:all\r\n"
        "\r\n"
    ).encode("ascii")
    out: List[Dict[str,str]] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.settimeout(timeout)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.sendto(req, MCAST)
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                data, (rip, _rport) = s.recvfrom(4096)
                raw = data.decode("utf-8", errors="ignore").split("\r\n")
                hdrs: Dict[str,str] = {"_ip": rip}
                for line in raw[1:]:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        hdrs[k.strip().lower()] = v.strip()
                out.append(hdrs)
            except socket.timeout:
                break
    except Exception:
        pass
    finally:
        try: s.close()
        except Exception: pass
    return out


def _fetch_xml(url: str, timeout: float = 0.9) -> str:
    try:
        u = urllib.parse.urlparse(url)
        port = u.port or (443 if u.scheme == "https" else 80)
        conn_cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(u.hostname, port, timeout=timeout)
        conn.request("GET", u.path or "/", headers={"Connection":"close", "User-Agent":"NHA/1.0"})
        resp = conn.getresponse()
        data = resp.read(65536)
        try: conn.close()
        except Exception: pass
        return (data or b"").decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _xml_text(root: ET.Element, tag_endswith: str) -> Optional[str]:
    for e in root.iter():
        if e.tag.lower().endswith(tag_endswith.lower()):
            t = (e.text or "").strip()
            if t:
                return t
    return None


def _parse_device_xml(xml_text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns (manufacturer, modelName, friendlyName)
    """
    try:
        root = ET.fromstring(xml_text)
        return (
            _xml_text(root, "manufacturer"),
            _xml_text(root, "modelname"),
            _xml_text(root, "friendlyname"),
        )
    except Exception:
        return None, None, None


def detect_on_lan(candidates: List[str], ssdp_timeout: float = 1.2, http_timeout: float = 0.8) -> Dict[str, Dict]:
    """
    Detect TP-Link Deco nodes among candidate IPs.
    Returns { ip: {"is_deco": bool, "model": str|None, "friendly_name": str|None, "manufacturer": str|None,
                    "evidence": [str], "source": "ssdp|http|both"} }
    """
    result: Dict[str, Dict] = {}

    # 1) SSDP pass — build ip->(manu,model,fn)
    by_ip: Dict[str, Dict[str,str]] = {}
    for hdrs in _ssdp_probe(timeout=ssdp_timeout):
        ip = hdrs.get("_ip")
        if not ip or ip not in candidates:
            continue
        loc = hdrs.get("location")
        manu = model = fn = None
        if loc:
            xml = _fetch_xml(loc, timeout=http_timeout)
            if xml:
                manu, model, fn = _parse_device_xml(xml)
        by_ip[ip] = {
            "manufacturer": manu or "",
            "model": model or "",
            "friendly_name": fn or "",
            "evidence": "; ".join([f"ssdp:{hdrs.get('st','')}", f"xml:{(model or '').strip()}"]).strip("; "),
            "source": "ssdp"
        }

    # 2) HTTP pass — add/merge HTTP fingerprints
    for ip in candidates:
        hdrs, body = _http_get_root(ip, timeout=http_timeout)
        title = _parse_html_title(body)
        server = hdrs.get("server","")
        evid_http = []
        if "tp-link" in server.lower() or "deco" in server.lower(): evid_http.append(f"server:{server}")
        if "deco" in (title.lower() if title else ""):              evid_http.append(f"title:{title}")
        if "tp-link" in (body.lower() if body else ""):             evid_http.append("body:tp-link")
        if title or server or evid_http:
            rec = by_ip.get(ip, {"manufacturer": "", "model": "", "friendly_name": "", "evidence": "", "source": ""})
            # Merge evidence
            old_e = rec.get("evidence","")
            rec["evidence"] = "; ".join([e for e in [old_e] + evid_http if e])
            rec["source"] = "both" if rec.get("source") == "ssdp" else "http"
            by_ip[ip] = rec

    # 3) Decide is_deco + model/friendly
    for ip, meta in by_ip.items():
        manu = meta.get("manufacturer","")
        model = meta.get("model","")
        fn    = meta.get("friendly_name","")
        evid  = meta.get("evidence","")

        is_deco = False
        # Multiple signals: manufacturer string, modelName containing 'Deco', HTTP hints
        if "tp-link" in manu.lower(): is_deco = True
        if re.search(r"\bdeco\b", model.lower() if model else ""): is_deco = True
        if "deco" in evid.lower(): is_deco = True

        result[ip] = {
            "is_deco": is_deco,
            "manufacturer": manu or ( "TP-Link" if is_deco else "" ),
            "model": model or None,
            "friendly_name": fn or None,
            "evidence": [e.strip() for e in (evid.split(";") if evid else []) if e.strip()],
            "source": meta.get("source") or "ssdp/http"
        }

    return result
