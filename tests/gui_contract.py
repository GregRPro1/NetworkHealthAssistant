# tests/gui_contract.py
import importlib, sys, inspect
from pathlib import Path
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP = QApplication.instance() or QApplication([])

def must_have(obj, names):
    missing = [n for n in names if not hasattr(obj, n)]
    return missing

def check_main():
    gm = importlib.import_module("gui_main")
    Main = getattr(gm, "Main", None)
    assert Main, "gui_main.Main missing"
    need = [
        "_port_open","ensure_api_server","toggle_api_server","closeEvent",
        "set_theme","refresh_status","kick_health_check","update_health",
        "export_report","run_speed_test","open_diagnostics","open_settings","show_about",
        "on_report_changed","on_ai_identify","on_fetch_threats","on_auto_advise",
    ]
    miss = must_have(Main, need)
    assert not miss, f"Main missing: {miss}"

def check_devices():
    td = importlib.import_module("tabs_devices")
    DevicesTab = getattr(td, "DevicesTab", None)
    assert DevicesTab, "tabs_devices.DevicesTab missing"
    need = ["on_scan","on_analyze","apply_filter","show_diagnostics_dialog","dataChanged"]
    miss = [n for n in need if not hasattr(DevicesTab, n)]
    assert not miss, f"DevicesTab missing: {miss}"
    # instance-level checks (model/table/_all_rows)
    inst = DevicesTab()
    need_inst = ["model","table","_all_rows"]
    miss_i = [n for n in need_inst if not hasattr(inst, n)]
    assert not miss_i, f"DevicesTab instance missing: {miss_i}"
    assert hasattr(inst.model, "setRows") and inspect.ismethod(inst.model.setRows), "DevicesModel.setRows missing"

def check_other_tabs():
    ti = importlib.import_module("tabs_identify")
    IdentifyTab = getattr(ti, "IdentifyTab", None)
    assert IdentifyTab and hasattr(IdentifyTab, "requestAi"), "IdentifyTab.requestAi signal missing"

    tt = importlib.import_module("tabs_threats")
    ThreatsTab = getattr(tt, "ThreatsTab", None)
    assert ThreatsTab, "ThreatsTab missing"
    for attr in ("requestThreats","requestAutoAdvice","show_text"):
        assert hasattr(ThreatsTab, attr), f"ThreatsTab.{attr} missing"

    ts = importlib.import_module("tabs_settings")
    SettingsTab = getattr(ts, "SettingsTab", None)
    assert SettingsTab and hasattr(SettingsTab, "themeChanged"), "SettingsTab.themeChanged missing"

    tw = importlib.import_module("tabs_wifi_survey")
    WifiSurveyTab = getattr(tw, "WifiSurveyTab", None)
    assert WifiSurveyTab and hasattr(WifiSurveyTab, "on_capture"), "WifiSurveyTab.on_capture missing"

def main():
    check_main()
    check_devices()
    check_other_tabs()
    print("GUI contract OK")

if __name__ == "__main__":
    sys.exit(main())
