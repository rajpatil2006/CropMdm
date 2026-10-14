// Copy this file to secrets.h and fill in your values.
// secrets.h is git-ignored so passwords never get committed.
#pragma once

// ---------- Wi-Fi ----------
#define WIFI_SSID      "your-wifi-name"
#define WIFI_PASSWORD  "your-wifi-password"

// ---------- HTTP sensor upload ----------
// Laptop on the same Wi-Fi: http://<laptop-LAN-IP>:8000/api/sensors/readings
#define API_URL        "http://192.168.0.101:8000/api/sensors/readings"

// ---------- Device identity ----------
// Admin console -> Devices -> Register device shows the key once.
#define DEVICE_ID      "ESP32_FARM_01"
#define DEVICE_KEY     "paste-the-key-from-the-admin-console"
