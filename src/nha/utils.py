import shutil, subprocess, json, os, datetime

def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def is_tool_on_path(name: str) -> bool:
    return shutil.which(name) is not None

def run_cmd_get_stdout(args, timeout=15):
    try:
        out = subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=timeout, text=True, shell=False)
        return out
    except Exception:
        return ""

def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path, obj):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
