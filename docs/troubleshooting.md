# Troubleshooting

- **iPhone app shows "No data"**: verify Base URL and token; ensure desktop API is running and reachable.
- **Speedtest fails**: install Ookla `speedtest` CLI or disable in Settings.
- **Printers not shown**: confirm ports 9100/631 reachable from the desktop machine.
- **Nmap enrichment missing**: install `nmap` and ensure it's on PATH.
- **Deco clients appear stuck on one node**: run `python -m src.nha.deco_mesh_diagnostics --quick`.
  The report shows the laptop's current Wi-Fi BSSID and stronger visible BSSIDs for the same SSID.
  Whole-home client-to-node distribution is only reported when the Deco API returns `ap_mac`/BSSID data;
  the tool no longer infers that distribution from LAN ping timings.
- **Deco node names are missing from the BSSID survey**: add each node's radio BSSID values under
  `integrations.deco.nodes[].bssids` in `config.yaml`. The node LAN MAC is often not the same as
  the Wi-Fi BSSID advertised by the mesh radio.
- **Laptop and desktop need to share survey results**: set `wifi_survey.output_dir` to the shared NAS
  path, for example `R:/NetworkHealthAssistant/wifi_surveys`. If `R:` is not available, the app falls
  back to local `data/wifi_surveys` for saving observations.
- **Internal Wi-Fi speed is missing**: install `iperf3` and run `iperf3 -s` on a wired LAN host, then set
  `health.iperf3.server` in Settings. Without iperf3, use the NAS file test as a practical laptop-to-NAS
  throughput check.
