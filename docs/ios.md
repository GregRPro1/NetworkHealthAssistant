# iOS App (SwiftUI)

## Desktop API
1. `pip install -r requirements.txt`
2. `python -m src.server.api`
3. Ensure your phone can reach `http://<desktop-ip>:8765` on the same LAN.

## iOS Project
1. Create a new SwiftUI iOS app in Xcode (iOS 16+).
2. Add the Swift files from the provided zip.
3. In the app Settings tab:
   - Base URL: `http://<desktop-ip>:8765`
   - Token: set to your `api.token`
4. Connect iPhone and press **Run** in Xcode.
   - With a free Apple ID, trust the developer profile on the device.
   - With a paid account, distribute via TestFlight.
