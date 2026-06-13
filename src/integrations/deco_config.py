from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


def normalize_mac(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    compact = re.sub(r"[^0-9a-fA-F]", "", raw)
    if len(compact) == 12:
        compact = compact.lower()
        return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
    return raw.lower().replace("-", ":")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _node_from_mapping(name_hint: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    name = str(raw.get("name") or name_hint or "").strip()
    ip = str(raw.get("ip") or raw.get("host") or "").strip()
    mac = normalize_mac(raw.get("mac") or raw.get("base_mac"))
    bssids = [normalize_mac(v) for v in _as_list(raw.get("bssids") or raw.get("bssid"))]
    bssids = [v for v in bssids if v]
    model = str(raw.get("model") or "").strip()
    return {
        "name": name,
        "ip": ip,
        "mac": mac,
        "bssids": sorted(set(bssids)),
        "model": model,
    }


def known_nodes_from_config(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    deco_cfg = ((cfg or {}).get("integrations", {}) or {}).get("deco", {}) or {}
    raw_nodes = deco_cfg.get("nodes") or {}
    nodes: Dict[str, Dict[str, Any]] = {}

    if isinstance(raw_nodes, dict):
        iterable: Iterable[tuple[str, Any]] = raw_nodes.items()
    elif isinstance(raw_nodes, list):
        iterable = ((str(i), node) for i, node in enumerate(raw_nodes))
    else:
        iterable = []

    for name_hint, raw in iterable:
        if not isinstance(raw, dict):
            continue
        node = _node_from_mapping(name_hint, raw)
        if node["ip"]:
            nodes[node["ip"]] = node

    return nodes


def merge_known_nodes(*node_sets: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for node_set in node_sets:
        for ip, node in (node_set or {}).items():
            existing = merged.setdefault(ip, {})
            existing.update({k: v for k, v in node.items() if v not in ("", [], None)})
            existing.setdefault("ip", ip)
    return merged
