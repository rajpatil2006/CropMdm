// CropMind ESP32 field node
//  * reads DHT11, soil, rain and ACS712 sensors and uploads them to the
//    CropMind backend over HTTP every few seconds
//  * the backend's reply to each upload can carry a pump command; the ESP32
//    runs the pump for the commanded time, then switches it off itself
//  * what happened to each command is reported in the next upload ("acks")
//
// No MQTT broker or other external service is needed. Based on
// esp32_motor_relay_acs712_1.ino. Libraries: DHT sensor library, ArduinoJson (v7).
// Wi-Fi details, the backend address and the device ID/key live in secrets.h.
// Register the device in the CropMind admin console to get its key.

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <math.h>

#include "secrets.h"

// ========== SENSOR PINS ==========
#define DHT_PIN       27
#define DHT_TYPE      DHT11

#define SOIL_PIN      34
#define RAIN_PIN      35
#define ACS_PIN       33
#define RELAY_PIN     26

DHT dht(DHT_PIN, DHT_TYPE);


const bool ENABLE_HTTP_UPLOAD = true;

// Confirm relay polarity with the pump power disconnected.
const bool RELAY_ACTIVE_LOW = false;

// ========== TEMPORARY CALIBRATION ==========
// These are examples, NOT measured calibration values.
// Replace after testing in dry and wet soil/water.

const int SOIL_DRY_RAW = 4095;
const int SOIL_WET_RAW = 1800;

const int RAIN_DRY_RAW = 4095;
const int RAIN_WET_RAW = 1500;

// ========== TIMING ==========
// Also how quickly a dashboard pump command reaches the pump.
const unsigned long SENSOR_INTERVAL_MS = 5000;
const unsigned long WIFI_RETRY_INTERVAL_MS = 15000;

// ========== PUMP SAFETY ==========
// Hard limit for any single pump run, whatever started it.
const unsigned long MAX_RUN_MS = 600UL * 1000UL;

// Local fallback: if the backend is unreachable for a long time, water on a
// simple soil threshold so the crop is not left dry (synopsis: works offline).
// Keep DISABLED until the soil sensor is calibrated - with the temporary
// calibration a 0 % reading would run the pump.
const bool ENABLE_LOCAL_FALLBACK = false;
const unsigned long FALLBACK_AFTER_MS = 30UL * 60UL * 1000UL;
const float LOCAL_ON_BELOW_PCT = 30.0;
const unsigned long LOCAL_RUN_SECONDS = 60;
const unsigned long LOCAL_COOLDOWN_MS = 45UL * 60UL * 1000UL;

unsigned long lastSensorRead = 0;
unsigned long lastWiFiAttempt = 0;
unsigned long lastBackendContactMs = 0;
unsigned long lastLocalRunMs = 0;

// ========== PUMP STATE ==========
bool relayIsOn = false;
unsigned long relayOnSinceMs = 0;
unsigned long pumpRunForMs = 0;   // 0 = no timed run active
String activeCommandId = "";
String lastCommandId = "";

// Command reports waiting to be sent with the next upload
const int MAX_PENDING_ACKS = 6;
struct Ack {
  String id;
  String status;
  String detail;
};
Ack pendingAcks[MAX_PENDING_ACKS];
int pendingAckCount = 0;

// ========== SENSOR VALUES ==========
float temperatureC = NAN;
float humidityPct = NAN;

int soilRawADC = 0;
int rainRawADC = 0;
int acsRawADC = 0;

float soilMoisturePct = NAN;
float rainWetnessPct = NAN;
float acsOutputVoltage = 0.0;

// ========== PERCENTAGE CONVERSION ==========
float calculatePercentage(int rawValue, int dryRaw, int wetRaw) {
  if (dryRaw == wetRaw) {
    return NAN;
  }
  float percentage = 100.0f * (dryRaw - rawValue) / (float)(dryRaw - wetRaw);
  return constrain(percentage, 0.0f, 100.0f);
}

// ========== RELAY CONTROL ==========
void setRelay(bool turnOn) {
  bool outputLevel = RELAY_ACTIVE_LOW ? !turnOn : turnOn;
  digitalWrite(RELAY_PIN, outputLevel ? HIGH : LOW);

  if (turnOn && !relayIsOn) {
    relayOnSinceMs = millis();
  }
  relayIsOn = turnOn;
  if (!turnOn) {
    pumpRunForMs = 0;
  }

  Serial.print("Relay command: ");
  Serial.println(turnOn ? "ON" : "OFF");
}

// Run the pump for a fixed time; servicePump() switches it off.
void runPumpFor(unsigned long seconds, const String& commandId) {
  unsigned long ms = min(seconds * 1000UL, MAX_RUN_MS);
  setRelay(true);
  relayOnSinceMs = millis();
  pumpRunForMs = ms;
  activeCommandId = commandId;
}

// ========== COMMAND REPORTS ==========
void queueAck(const String& id, const char* status, const char* detail) {
  if (id.length() == 0 || id == "local-fallback") {
    return;
  }
  if (pendingAckCount >= MAX_PENDING_ACKS) {
    // Drop the oldest report to make room
    for (int i = 1; i < MAX_PENDING_ACKS; i++) {
      pendingAcks[i - 1] = pendingAcks[i];
    }
    pendingAckCount--;
  }
  pendingAcks[pendingAckCount++] = {id, String(status), String(detail ? detail : "")};
  Serial.printf("Command %s: %s\n", id.c_str(), status);
}

// ========== COMMANDS FROM THE BACKEND ==========
void handleCommand(JsonObjectConst command) {
  String id = command["id"] | "";
  String action = command["action"] | "";
  unsigned long seconds = command["seconds"] | 0UL;

  if (id.length() == 0 || id == lastCommandId) {
    return;  // nothing new (the backend may resend until it hears back)
  }
  lastCommandId = id;
  Serial.printf("Backend command %s: %s %lus\n", id.c_str(), action.c_str(), seconds);

  if (action == "OFF") {
    if (activeCommandId.length() > 0) {
      queueAck(activeCommandId, "stopped", "stopped by OFF command");
      activeCommandId = "";
    }
    setRelay(false);
    queueAck(id, "done", "pump off");
  } else if (action == "ON") {
    if (seconds == 0 || seconds * 1000UL > MAX_RUN_MS) {
      queueAck(id, "rejected", "invalid run time");
      return;
    }
    if (activeCommandId.length() > 0) {
      queueAck(activeCommandId, "stopped", "replaced by newer command");
    }
    runPumpFor(seconds, id);
    queueAck(id, "started", nullptr);
  } else {
    queueAck(id, "rejected", "unknown action");
  }
}

// ========== PUMP TIMERS / SAFETY ==========
void servicePump() {
  unsigned long now = millis();

  // Timed run finished
  if (relayIsOn && pumpRunForMs > 0 && now - relayOnSinceMs >= pumpRunForMs) {
    setRelay(false);
    queueAck(activeCommandId, "done", "run time completed");
    activeCommandId = "";
  }

  // Hard limit, also covers a manual serial relay_on
  if (relayIsOn && now - relayOnSinceMs >= MAX_RUN_MS) {
    Serial.println("Safety: maximum run time reached");
    setRelay(false);
    queueAck(activeCommandId, "stopped", "maximum run time");
    activeCommandId = "";
  }

  // Offline fallback on a simple soil threshold
  if (ENABLE_LOCAL_FALLBACK && !relayIsOn
      && now - lastBackendContactMs >= FALLBACK_AFTER_MS
      && (lastLocalRunMs == 0 || now - lastLocalRunMs >= LOCAL_COOLDOWN_MS)
      && !isnan(soilMoisturePct) && soilMoisturePct < LOCAL_ON_BELOW_PCT
      && !(rainWetnessPct >= 50.0)) {
    Serial.println("Backend unreachable - local fallback irrigation");
    lastLocalRunMs = now;
    runPumpFor(LOCAL_RUN_SECONDS, "local-fallback");
  }
}

// ========== WIFI ==========
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long now = millis();
  if (now - lastWiFiAttempt < WIFI_RETRY_INTERVAL_MS) {
    return;
  }
  lastWiFiAttempt = now;

  Serial.println("Connecting to Wi-Fi...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// ========== SENSOR READING ==========
void readSensors() {
  float newTemperature = dht.readTemperature();
  float newHumidity = dht.readHumidity();

  if (!isnan(newTemperature)) {
    temperatureC = newTemperature;
  }
  if (!isnan(newHumidity)) {
    humidityPct = newHumidity;
  }

  soilRawADC = analogRead(SOIL_PIN);
  rainRawADC = analogRead(RAIN_PIN);
  acsRawADC = analogRead(ACS_PIN);

  soilMoisturePct = calculatePercentage(soilRawADC, SOIL_DRY_RAW, SOIL_WET_RAW);
  rainWetnessPct = calculatePercentage(rainRawADC, RAIN_DRY_RAW, RAIN_WET_RAW);

  // Approximate ADC input voltage, not calibrated current.
  acsOutputVoltage = (acsRawADC / 4095.0f) * 3.3f;

  Serial.println("\n========== SENSOR DATA ==========");
  Serial.printf("Temperature: %.1f C | Humidity: %.1f %%\n", temperatureC, humidityPct);
  Serial.printf("Soil raw ADC: %d | Moisture: %.1f%%\n", soilRawADC, soilMoisturePct);
  Serial.printf("Rain raw ADC: %d | Wetness: %.1f%%\n", rainRawADC, rainWetnessPct);
  Serial.printf("ACS raw ADC: %d | %.3f V\n", acsRawADC, acsOutputVoltage);
  if (WiFi.status() == WL_CONNECTED) {
    // Which network and address - must match the laptop's network for uploads to work
    Serial.printf("Wi-Fi: CONNECTED to \"%s\" | ESP32 IP %s | gateway %s | signal %d dBm\n",
                  WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(),
                  WiFi.gatewayIP().toString().c_str(), WiFi.RSSI());
    Serial.printf("Uploading to: %s\n", API_URL);
  } else {
    Serial.println("Wi-Fi: OFFLINE");
  }
  Serial.printf("Relay: %s", relayIsOn ? "ON" : "OFF");
  if (relayIsOn && pumpRunForMs > 0) {
    Serial.printf(" (%lus left)", (pumpRunForMs - (millis() - relayOnSinceMs)) / 1000UL);
  }
  Serial.println("\n=================================");
}

// ========== HTTP UPLOAD (+ command in the response) ==========
void uploadReadings() {
  if (!ENABLE_HTTP_UPLOAD) {
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Upload skipped: Wi-Fi unavailable");
    return;
  }
  if (isnan(temperatureC) || isnan(humidityPct)) {
    Serial.println("Upload skipped: invalid DHT reading");
    return;
  }

  HTTPClient http;
  // Hosted backends (Render etc.) use HTTPS; the laptop uses plain HTTP.
  // A sleeping free server can take up to a minute to wake, so allow longer there.
  static WiFiClientSecure secureClient;
  static WiFiClient plainClient;
  bool secure = strncmp(API_URL, "https://", 8) == 0;
  bool started;
  if (secure) {
    // Encrypts the connection. For production, pin the server's root CA with
    // secureClient.setCACert(...) so the server's identity is also checked.
    secureClient.setInsecure();
    http.setTimeout(20000);
    started = http.begin(secureClient, API_URL);
  } else {
    http.setTimeout(3000);
    started = http.begin(plainClient, API_URL);
  }
  if (!started) {
    Serial.println("Could not initialize HTTP connection");
    return;
  }
  http.addHeader("Content-Type", "application/json");
  // Proves to the backend that this upload really comes from this device
  http.addHeader("X-Device-Key", DEVICE_KEY);

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["temperature"] = serialized(String(temperatureC, 1));
  doc["humidity"] = serialized(String(humidityPct, 1));
  doc["soil_raw_adc"] = soilRawADC;
  doc["soil_moisture_pct"] = serialized(String(soilMoisturePct, 1));
  doc["rain_raw_adc"] = rainRawADC;
  doc["rain_wetness_pct"] = serialized(String(rainWetnessPct, 1));
  doc["acs_raw_adc"] = acsRawADC;
  doc["acs_output_voltage_estimate"] = serialized(String(acsOutputVoltage, 3));
  doc["relay_on"] = relayIsOn;

  int sentAcks = pendingAckCount;
  if (sentAcks > 0) {
    JsonArray acks = doc["acks"].to<JsonArray>();
    for (int i = 0; i < sentAcks; i++) {
      JsonObject a = acks.add<JsonObject>();
      a["id"] = pendingAcks[i].id;
      a["status"] = pendingAcks[i].status;
      if (pendingAcks[i].detail.length() > 0) {
        a["detail"] = pendingAcks[i].detail;
      }
    }
  }

  String payload;
  serializeJson(doc, payload);
  int httpCode = http.POST(payload);
  Serial.printf("HTTP response code: %d\n", httpCode);

  if (httpCode >= 200 && httpCode < 300) {
    lastBackendContactMs = millis();

    // Reports were delivered; keep only ones added after this upload started
    for (int i = sentAcks; i < pendingAckCount; i++) {
      pendingAcks[i - sentAcks] = pendingAcks[i];
    }
    pendingAckCount -= sentAcks;

    JsonDocument response;
    if (!deserializeJson(response, http.getString())) {
      JsonObjectConst command = response["command"];
      if (!command.isNull()) {
        handleCommand(command);
      }
    }
  } else if (httpCode == 401) {
    Serial.println("Upload refused: register this device in the admin console and put its key in secrets.h");
  } else {
    Serial.println("Upload failed; check server and network");
  }
  http.end();
}

// ========== SERIAL TEST COMMANDS ==========
void processSerialCommands() {
  if (!Serial.available()) {
    return;
  }
  String command = Serial.readStringUntil('\n');
  command.trim();
  command.toLowerCase();

  if (command == "relay_off") {
    setRelay(false);
    activeCommandId = "";
  } else if (command == "relay_on") {
    // Test only with pump power disconnected. Stops after MAX_RUN_MS.
    setRelay(true);
  } else if (command == "read") {
    readSensors();
  } else {
    Serial.println("Commands: read, relay_on, relay_off");
  }
}

// ========== SETUP ==========
void setup() {
  Serial.begin(115200);
  delay(1000);

  // Initialize the relay output to the configured OFF level.
  digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW);
  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);

  analogReadResolution(12);
  dht.begin();

  Serial.println("\nCropMind ESP32 starting");
  Serial.printf("Local fallback irrigation: %s\n", ENABLE_LOCAL_FALLBACK ? "ENABLED" : "DISABLED");

  WiFi.mode(WIFI_STA);
  connectWiFi();
}

// ========== MAIN LOOP ==========
void loop() {
  connectWiFi();
  processSerialCommands();
  servicePump();

  unsigned long now = millis();
  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;
    readSensors();
    uploadReadings();
  }

  delay(10);
}
