import os
from .utils import read_json, write_json

def paths(root="./data"):
    return {
        "root": root,
        "current": os.path.join(root, "current_scan.json"),
        "baseline": os.path.join(root, "baseline.json"),
        "report_json": os.path.join(root, "report.json"),
        "report_md": os.path.join(root, "report.md"),
        "ai_payload": os.path.join(root, "ai_payload.json"),
    }

def load_current(root):
    return read_json(paths(root)["current"], default={"devices": []})

def save_current(root, devices):
    write_json(paths(root)["current"], {"devices": devices})

def load_baseline(root):
    return read_json(paths(root)["baseline"], default={"devices": []})

def save_baseline(root, devices):
    write_json(paths(root)["baseline"], {"devices": devices})
