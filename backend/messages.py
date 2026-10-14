"""
English text for decision message codes.

Decisions carry reasons as {"key", "params"} so the dashboard can show them in
English, Marathi or Hindi (frontend/src/i18n). This English rendering is used
for logs, the audit trail and API clients that do not translate.
"""

ENGLISH = {
    "water.ok": "Root zone has used {used} mm of the {raw} mm the {crop} ({stage} stage) can use "
                "without stress; stress begins in about {hours} h.",
    "water.stressed": "Root zone has used {used} mm, beyond the {raw} mm the {crop} ({stage} stage) "
                      "tolerates; it can safely wait about {hours} h more.",
    "ai.wait": "AI model expects enough rain within the {hours} h the crop can safely wait "
               "({conf}% confidence, learned from past forecasts vs. actual rainfall).",
    "ai.irrigate": "AI model does not expect enough rain in time ({conf}% confidence).",
    "guard.no_irrigation": "Safety guard: soil still holds readily available water, so no irrigation.",
    "guard.must_irrigate": "Safety guard: crop is past its safe-wait limit, so it cannot wait for rain.",
    "guard.no_skip": "Safety guard: crop is past its comfort zone, so 'no irrigation' was not allowed.",
    "rule.differs": "A forecast-only rule would have chosen '{action}'.",
    "trust.soil_adc_limit": "Soil sensor reads {raw}, the limit of the ESP32 input: the sensor is disconnected, on the wrong pin or powered with too high a voltage.",
    "trust.soil_missing": "Soil moisture reading is missing.",
    "trust.soil_range": "Soil moisture reading {value}% is outside 0-100%.",
    "trust.no_timestamp": "Sensor reading has no timestamp.",
    "trust.stale": "Latest sensor reading is {age} min old (limit {limit} min).",
    "trust.checks_off": "Sensor fault checks are OFF for this device (test mode) - readings are trusted as they are.",
    "trust.hold": "Pump held OFF until the data can be trusted.",
}


def render(message):
    template = ENGLISH.get(message["key"], message["key"])
    try:
        return template.format(**message.get("params", {}))
    except (KeyError, IndexError, ValueError):
        return template


def msg(key, **params):
    return {"key": key, "params": params}
