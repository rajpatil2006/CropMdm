"""Request/response models shared by the API routers."""

import re
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from crops import CROPS, SOILS

LANGUAGES = ("en", "mr", "hi")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")


# ---------------------------------------------------------------- accounts

class RegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(default="", max_length=20)
    village: str = Field(default="", max_length=80)
    language: Literal["en", "mr", "hi"] = "en"

    @field_validator("username")
    @classmethod
    def check_username(cls, value):
        value = value.strip().lower()
        if not USERNAME_RE.match(value):
            raise ValueError("Username: 3-30 characters, lowercase letters, digits, _ or .")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    phone: Optional[str] = Field(default=None, max_length=20)
    village: Optional[str] = Field(default=None, max_length=80)
    language: Optional[Literal["en", "mr", "hi"]] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------- devices

class DeviceCreate(BaseModel):
    device_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{3,40}$")
    name: str = Field(min_length=1, max_length=80)
    owner: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    owner: Optional[str] = None        # "" unassigns
    unassign: bool = False


class SensorReading(BaseModel):
    device_id: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    soil_raw_adc: Optional[int] = None
    soil_moisture_pct: Optional[float] = None
    rain_raw_adc: Optional[int] = None
    rain_wetness_pct: Optional[float] = None
    acs_raw_adc: Optional[int] = None
    acs_output_voltage_estimate: Optional[float] = None
    relay_on: bool = False
    timestamp: Optional[datetime] = None
    # ESP32's reports on pump commands it received: [{"id", "status", "detail"}]
    acks: Optional[list[dict]] = None


class PumpCommand(BaseModel):
    action: Literal["ON", "OFF"]
    seconds: int = Field(default=0, ge=0, le=600)


# ---------------------------------------------------------------- crop config

class CustomCrop(BaseModel):
    """Any crop not in the FAO-56 table: give its own FAO-56 style parameters."""

    name: str = "Custom crop"
    kc_ini: float = Field(gt=0, le=1.5)
    kc_mid: float = Field(gt=0, le=1.5)
    kc_end: float = Field(gt=0, le=1.5)
    stage_days: list[int] = Field(min_length=4, max_length=4)
    p: float = Field(ge=0.05, le=0.9)
    stress_tolerance: Optional[float] = Field(default=None, ge=0, le=0.9)

    @model_validator(mode="after")
    def check_stages(self):
        if any(d <= 0 for d in self.stage_days):
            raise ValueError("Each stage must last at least 1 day")
        return self


class FarmConfig(BaseModel):
    """Per-device crop, soil, pot and location settings."""

    device_id: str = ""
    crop: str = "tomato"           # FAO-56 table key, or "custom"
    custom_crop: Optional[CustomCrop] = None
    sowing_date: date = Field(default_factory=lambda: date.today() - timedelta(days=30))
    soil_type: str = "potting_mix"
    # Optional calibration in the soil sensor's own % units
    # (FC: reading 24 h after saturating and draining the pot)
    field_capacity_pct: Optional[float] = Field(default=None, gt=0, le=100)
    wilting_point_pct: Optional[float] = Field(default=None, ge=0, lt=100)
    root_depth_mm: float = Field(default=200, gt=0, le=2000)
    pot_area_cm2: float = Field(default=700, gt=0)
    pump_flow_ml_per_min: float = Field(default=1200, gt=0)
    max_pump_seconds: float = Field(default=300, gt=0)
    latitude: float = Field(default=18.6517, ge=-90, le=90)
    longitude: float = Field(default=73.7616, ge=-180, le=180)
    rain_probability_threshold: int = Field(default=60, ge=0, le=100)
    rain_cover_fraction: float = Field(default=0.5, gt=0, le=2)
    # Let CropMind switch the pump by itself (off until the soil sensor is calibrated)
    auto_irrigation: bool = False
    # Sensor fault checks (e.g. soil sensor stuck at the ADC limit). Turn off only
    # for bench tests without a pot - decisions then trust the raw readings.
    sensor_checks: bool = True

    @model_validator(mode="after")
    def check_values(self):
        if self.crop == "custom":
            if self.custom_crop is None:
                raise ValueError("Crop 'custom' needs custom_crop parameters")
        elif self.crop not in CROPS:
            raise ValueError(f"Unknown crop '{self.crop}'. Options: {', '.join(CROPS)}, custom")
        if self.soil_type not in SOILS:
            raise ValueError(f"Unknown soil '{self.soil_type}'. Options: {', '.join(SOILS)}")
        if self.sowing_date > date.today():
            raise ValueError("Sowing date cannot be in the future")
        soil = SOILS[self.soil_type]
        fc = self.field_capacity_pct or soil["fc"]
        wp = self.wilting_point_pct or soil["wp"]
        if fc <= wp:
            raise ValueError("Field capacity must be greater than wilting point")
        return self
