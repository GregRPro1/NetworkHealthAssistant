# src/nha/registry.py
from __future__ import annotations
import sqlite3, json, time
from pathlib import Path
from typing import Dict, List, Any, Iterable

DB_PATH = Path("./data/registry.db")

DDL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS devices(
  mac TEXT PRIMARY KEY,
  first_seen INTEGER,
  last_seen  INTEGER,
  vendor     TEXT,
  notes      TEXT
);
CREATE TABLE IF NOT EXISTS sightings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  mac TEXT,            -- may be NULL if unknown
  ip  TEXT NOT NULL,
  hostname TEXT,
  vendor TEXT,
  category TEXT,
  sources TEXT,        -- JSON list e.g. ["arp","icmp","ssdp"]
  segment TEXT,        -- subnet (e.g. 192.168.1.0/24) or other label
  ssid TEXT,           -- when available via router plugin
  vlan_id INTEGER,     -- when available via router plugin
  FOREIGN KEY(mac) REFERENCES devices(mac)
);
CREATE INDEX IF NOT EXISTS idx_sight_ts ON sightings(ts);
CREATE INDEX IF NOT EXISTS idx_sight_mac ON sightings(mac);
"""

def _cx():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(DB_PATH)
    cx.execute("PRAGMA foreign_keys=ON")
    return cx

def init():
    with _cx() as cx:
        for stmt in DDL.strip().split(";\n"):
            if stmt.strip():
                cx.execute(stmt)

def record_sighting(dev: Dict[str, Any], segment: str|None, sources: Iterable[str]):
    """
    dev: {"ip", "mac"?, "hostname"?, "vendor"?, "category"?}
    segment: subnet label (e.g., "192.168.1.0/24")
    sources: iterable of discovery methods that saw the device this cycle
    """
    ts = int(time.time())
    src = json.dumps(sorted(set(sources)))
    mac = (dev.get("mac") or "").lower() or None
    ip  = dev.get("ip","")
    hostname = dev.get("hostname") or ""
    vendor   = dev.get("vendor") or ""
    category = dev.get("category") or ""

    with _cx() as cx:
        if mac:
            # upsert devices row
            row = cx.execute("SELECT mac FROM devices WHERE mac=?", (mac,)).fetchone()
            if row:
                cx.execute("UPDATE devices SET last_seen=?, vendor=COALESCE(NULLIF(?,''),vendor) WHERE mac=?",
                           (ts, vendor, mac))
            else:
                cx.execute("INSERT INTO devices(mac,first_seen,last_seen,vendor,notes) VALUES(?,?,?,?,?)",
                           (mac, ts, ts, vendor, ""))

        cx.execute("""INSERT INTO sightings(ts,mac,ip,hostname,vendor,category,sources,segment,ssid,vlan_id)
                      VALUES(?,?,?,?,?,?,?,?,NULL,NULL)""",
                   (ts, mac, ip, hostname, vendor, category, src, segment))

def record_many(devices: List[Dict[str, Any]], segment: str|None, sources_map: Dict[str, List[str]]):
    """
    devices: list of device dicts.
    sources_map: ip -> list of sources seen this cycle.
    """
    init()
    for d in devices:
        srcs = sources_map.get(d.get("ip",""), []) or []
        record_sighting(d, segment, srcs)

def device_timeline(mac: str) -> List[Dict[str, Any]]:
    init()
    with _cx() as cx:
        rows = cx.execute("SELECT ts,ip,hostname,category,sources,segment,ssid,vlan_id FROM sightings WHERE mac=? ORDER BY ts",
                          (mac.lower(),)).fetchall()
    out = []
    for (ts, ip, hn, cat, src, seg, ssid, vlan) in rows:
        out.append({
            "ts": ts, "ip": ip, "hostname": hn, "category": cat,
            "sources": json.loads(src or "[]"), "segment": seg,
            "ssid": ssid, "vlan_id": vlan
        })
    return out

def inventory_snapshot(age_seconds: int = 24*3600) -> List[Dict[str, Any]]:
    """
    Return one row per MAC (or per IP if MAC missing) seen in the last N seconds.
    """
    cutoff = int(time.time()) - age_seconds
    init()
    with _cx() as cx:
        rows = cx.execute("""
        SELECT s.mac, s.ip, s.hostname, s.vendor, s.category, s.sources, s.segment, s.ssid, s.vlan_id, MAX(s.ts) as last_ts
        FROM sightings s
        WHERE s.ts >= ?
        GROUP BY COALESCE(s.mac, s.ip)
        ORDER BY last_ts DESC
        """, (cutoff,)).fetchall()
    out = []
    for mac, ip, hn, vendor, cat, src, seg, ssid, vlan, last_ts in rows:
        out.append({
            "mac": mac, "ip": ip, "hostname": hn, "vendor": vendor, "category": cat,
            "sources": sorted(set((json.loads(src or "[]")))),
            "segment": seg, "ssid": ssid, "vlan_id": vlan, "last_seen": last_ts
        })
    return out
