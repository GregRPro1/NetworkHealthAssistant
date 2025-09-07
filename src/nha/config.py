import os, yaml
from .utils import ensure_dir

DEFAULTS = {
    "network": {"cidr": "192.168.1.0/24"},
    "scanner": {"use_nmap_if_available": True},
    "storage": {"root": "./data"}
}

def load_config(path="./config.yaml"):
    cfg = DEFAULTS.copy()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            for k, v in user.items():
                if isinstance(v, dict) and k in cfg:
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception:
            pass
    ensure_dir(cfg["storage"]["root"])
    return cfg
