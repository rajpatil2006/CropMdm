// Turns one SHAP contribution into a plain sentence a farmer understands.
// Returns {key, params}: the key is a "why.*" translation, params fill it in.

const STAGES = ["initial", "development", "mid", "late"];

export function impactLevel(shap) {
  const size = Math.abs(shap);
  if (size >= 0.2) return "strong";
  if (size >= 0.07) return "medium";
  return "small";
}

export function farmerFact(c, { crop, monthName, stageName }) {
  const v = c.value;
  const n = (x, digits = 0) => (Math.round(x * 10 ** digits) / 10 ** digits).toString();

  switch (c.feature) {
    case "depletion_vs_raw_pct":
      if (v >= 100) return { key: "why.soilTooDry", params: { crop } };
      if (v >= 70) return { key: "why.soilDrying", params: {} };
      return { key: "why.soilOk", params: {} };
    case "depletion_pct":
      return { key: "why.waterUsed", params: { v: n(v) } };
    case "hours_crop_can_wait":
      return v <= 0 ? { key: "why.cannotWait", params: {} } : { key: "why.canWait", params: { h: n(v) } };
    case "taw_mm":
      return { key: "why.soilCapacity", params: { v: n(v) } };
    case "etc_mm_day":
      return { key: "why.cropUse", params: { v: n(v, 1) } };
    case "et0_mm":
      return { key: "why.weatherDrying", params: { v: n(v, 1) } };
    case "kc":
    case "stage_index":
      return { key: "why.stage", params: { stage: stageName(STAGES[Math.round(v)] ?? "mid") } };
    case "crop_p":
      if (v < 0.35) return { key: "why.cropSensitive", params: { crop } };
      if (v >= 0.5) return { key: "why.cropHardy", params: { crop } };
      return { key: "why.cropMedium", params: { crop } };
    case "stress_tolerance":
      return v < 0.2 ? { key: "why.shortWait", params: { crop } } : { key: "why.longWait", params: { crop } };
    case "tmax_c":
      return v >= 34 ? { key: "why.hot", params: { v: n(v) } } : { key: "why.temp", params: { v: n(v) } };
    case "humidity_pct":
      if (v >= 70) return { key: "why.humid", params: { v: n(v) } };
      if (v < 45) return { key: "why.dryAir", params: { v: n(v) } };
      return { key: "why.humidity", params: { v: n(v) } };
    case "raining_now":
      return { key: v ? "why.rainingNow" : "why.notRaining", params: {} };
    case "forecast_available":
      return { key: v ? "why.forecastOk" : "why.noForecast", params: {} };
    case "forecast_rain_24h_mm":
      return v < 0.5 ? { key: "why.noRain24", params: {} } : { key: "why.rain24", params: { v: n(v, 1) } };
    case "forecast_rain_48h_mm":
      return v < 0.5 ? { key: "why.noRain48", params: {} } : { key: "why.rain48", params: { v: n(v, 1) } };
    case "hours_until_rain":
      return v >= 72 ? { key: "why.noRainSoon", params: {} } : { key: "why.rainIn", params: { h: n(v) } };
    case "month":
      return { key: "why.month", params: { month: monthName(Math.round(v)) } };
    default:
      return { key: c.feature, params: {} };
  }
}

/** "3 min 16 s" style duration. */
export function minutesSeconds(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return { m, s };
}
