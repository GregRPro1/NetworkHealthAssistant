"""
AI bridge that tries to reuse Persistent Assistant's AI client if present.
Configure via config.yaml:

ai:
  persistent_assistant_path: "C:/_Repos/PersistentAssistant"   # Windows path
  entrypoint: "pa.ai_client:analyze_inventory"                 # module:function in PA

If not found, falls back to local stub (src/nha/ai_client.py).
"""

import sys, os, importlib
from src.nha.ai_client import analyze_with_ai as local_analyze

def analyze_with_ai(inventory: dict, cfg: dict) -> dict:
    ai_cfg = (cfg or {}).get("ai", {})
    pa_path = ai_cfg.get("persistent_assistant_path")
    entry = ai_cfg.get("entrypoint", "pa.ai_client:analyze_inventory")

    if pa_path and os.path.isdir(pa_path):
        if pa_path not in sys.path:
            sys.path.insert(0, pa_path)
        try:
            mod_name, func_name = entry.split(":")
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, func_name)
            return fn(inventory)  # expect dict
        except Exception as e:
            # Fall back if import/call fails
            return {"error": f"PA AI bridge failed: {e}", **local_analyze(inventory)}
    # Fallback to local
    return local_analyze(inventory)
