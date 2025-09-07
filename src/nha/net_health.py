import shutil, subprocess, sys, socket, json, time, platform

def _ping_cmd(host: str):
    # Windows uses -n, Unix uses -c
    count_flag = "-n" if platform.system().lower().startswith("win") else "-c"
    return ["ping", count_flag, "1", "-w", "2000", host]

def ping_ms(host: str, timeout=5) -> float | None:
    try:
        out = subprocess.check_output(_ping_cmd(host), stderr=subprocess.STDOUT, timeout=timeout, text=True)
    except Exception:
        return None
    # Parse ms from output
    text = out.lower().replace("=", " ").replace("<", "")
    # Try common patterns
    for token in text.split():
        if token.endswith("ms"):
            try:
                val = float(token.replace("ms",""))
                if val > 0:
                    return val
            except Exception:
                continue
    # Windows summary often has "Average = 12ms"
    for line in text.splitlines():
        if "average" in line and "ms" in line:
            # find last number before "ms"
            parts = line.split()
            for i,p in enumerate(parts):
                if p.endswith("ms"):
                    try:
                        return float(p.replace("ms",""))
                    except Exception:
                        pass
    return None

def tcp_open(ip: str, port: int, timeout=1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def speedtest(binary: str | None = None, timeout=60) -> dict | None:
    # Prefer Ookla 'speedtest' if present, else try 'speedtest-cli'
    bins = [binary] if binary else []
    if not bins:
        for b in ["speedtest", "speedtest-cli"]:
            if shutil.which(b):
                bins.append(b)
    if not bins:
        return None
    b = bins[0]
    args = [b]
    if "speedtest" in b and "--format=json" in _supported_args(b):
        args += ["--format=json"]
    elif "speedtest-cli" in b:
        args += ["--json"]
    try:
        out = subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        data = json.loads(out)
        # Normalize
        down = None; up = None; ping = None
        if "download" in data and isinstance(data["download"], dict) and "bandwidth" in data["download"]:
            # Ookla returns bits/s in "bandwidth" *not* Mbps; convert
            down = data["download"].get("bandwidth")
            up = data.get("upload", {}).get("bandwidth")
            if down is not None: down = round(down/125000, 2)  # to Mbps
            if up is not None: up = round(up/125000, 2)
            ping = data.get("ping", {}).get("latency")
        elif "download" in data and isinstance(data["download"], (int, float)):
            # speedtest-cli returns bits/s; convert to Mbps
            down = round(data["download"]/1_000_000, 2)
            up = round(data.get("upload",0)/1_000_000, 2)
            ping = data.get("ping")
        return {"down_mbps": down, "up_mbps": up, "ping_ms": ping, "raw": data}
    except Exception:
        return None

def _supported_args(binary: str):
    try:
        out = subprocess.check_output([binary, "--help"], stderr=subprocess.STDOUT, timeout=5, text=True)
        return out
    except Exception:
        return ""

def iperf3_test(server: str, timeout=20) -> dict | None:
    if not shutil.which("iperf3"):
        return None
    try:
        out = subprocess.check_output(["iperf3", "-c", server, "-J"], stderr=subprocess.STDOUT, timeout=timeout, text=True)
        data = json.loads(out)
        bps = data.get("end", {}).get("sum_received", {}).get("bits_per_second")
        if bps is not None:
            return {"lan_mbps": round(bps/1_000_000, 2), "raw": data}
    except Exception:
        return None
    return None
