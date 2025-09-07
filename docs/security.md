# Security Best Practices

- Set a strong `api.token` in `config.yaml` and do not share it.
- Consider binding the API to a LAN interface only.
- Segment IoT devices to a dedicated VLAN/SSID. Block IoT→LAN by default.
- Disable router WPS and UPnP. Keep firmware updated.
- Use WPA2/WPA3 with strong passphrases.
