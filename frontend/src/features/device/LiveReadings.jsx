import { useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CloudRain, Droplets, Power, Thermometer, Wind, Zap } from "lucide-react";
import api from "../../api";
import { EmptyState, MetricCard, Panel } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";
import { formatDateTime } from "../../utils/format";

const HISTORY_POINTS = 120; // about 10 minutes at one reading every 5 s

// One chart per sensor, two per row
const SENSORS = [
  { key: "temperature", label: "device.temperature", unit: "°C", color: "#e76f51", icon: Thermometer },
  { key: "humidity", label: "device.humidity", unit: "%", color: "#3686e8", icon: Wind, domain: [0, 100] },
  { key: "soil", label: "device.soilMoisture", unit: "%", color: "#239b76", icon: Droplets, domain: [0, 100] },
  { key: "current", label: "device.current", unit: "V", color: "#b26ad9", icon: Zap, note: "device.currentNote" },
  { key: "rain", label: "device.rainWetness", unit: "%", color: "#6585db", icon: CloudRain, domain: [0, 100] },
  { key: "pump", label: "device.pumpRelay", unit: "", color: "#1f6fd1", icon: Power, domain: [0, 1], step: true },
];

function SensorChart({ sensor, data, t }) {
  const Icon = sensor.icon;
  const values = data.map((d) => d[sensor.key]).filter((v) => v != null);
  const latest = values.length ? values[values.length - 1] : null;
  const shown = sensor.key === "pump"
    ? latest == null ? "--" : latest ? t("pump.on") : t("pump.off")
    : latest == null ? "--" : `${latest} ${sensor.unit}`;

  return (
    <Panel
      className="sensor-chart"
      title={t(sensor.label)}
      subtitle={sensor.note ? t(sensor.note) : t("device.chartRecent", { n: data.length })}
      actions={<strong className="sensor-chart-value" style={{ color: sensor.color }}>{shown}</strong>}
      icon={<Icon size={19} color={sensor.color} />}
    >
      {values.length === 0 ? (
        <EmptyState>{t("device.noHistory")}</EmptyState>
      ) : (
        <ResponsiveContainer width="100%" height={170}>
          <AreaChart data={data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
            <defs>
              <linearGradient id={`fill-${sensor.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={sensor.color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={sensor.color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2ee" vertical={false} />
            <XAxis dataKey="time" tick={{ fontSize: 10 }} minTickGap={40} tickLine={false} />
            <YAxis
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              domain={sensor.domain ?? ["auto", "auto"]}
              ticks={sensor.step ? [0, 1] : undefined}
              // At most 2 decimals, so values like 27.375 are not cut off
              tickFormatter={sensor.step ? (v) => (v ? t("pump.on") : t("pump.off")) : (v) => parseFloat(v.toFixed(2))}
              width={sensor.step ? 48 : 44}
            />
            <Tooltip
              formatter={(v) => [sensor.step ? (v ? t("pump.on") : t("pump.off")) : `${v} ${sensor.unit}`, t(sensor.label)]}
            />
            <Area
              type={sensor.step ? "stepAfter" : "monotone"}
              dataKey={sensor.key}
              stroke={sensor.color}
              strokeWidth={2}
              fill={`url(#fill-${sensor.key})`}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}

export default function LiveReadings({ deviceId }) {
  const { t, locale } = useI18n();
  const [reading, setReading] = useState(null);
  const [history, setHistory] = useState([]);

  usePolling(
    (isActive) =>
      Promise.all([
        api.get(`/api/devices/${deviceId}/readings/latest`),
        api.get(`/api/devices/${deviceId}/readings`, { params: { limit: HISTORY_POINTS } }),
      ])
        .then(([latest, past]) => {
          if (!isActive()) return;
          setReading(latest.data?.timestamp ? latest.data : null);
          setHistory(
            past.data
              .slice()
              .reverse()
              .map((r) => ({
                time: new Date(r.timestamp).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
                temperature: r.temperature ?? null,
                humidity: r.humidity ?? null,
                soil: r.soil_moisture_pct ?? null,
                current: r.acs_output_voltage_estimate ?? null,
                rain: r.rain_wetness_pct ?? null,
                pump: r.relay_on ? 1 : 0,
              }))
          );
        })
        .catch(() => {}),
    5000,
    [deviceId, locale]
  );

  return (
    <section className="live-readings">
      <div className="section-heading">
        <h3>{t("device.liveReadings")}</h3>
        <span className="last-updated">
          {reading ? t("device.lastRecord", { time: formatDateTime(reading.timestamp, locale) }) : t("device.waiting")}
        </span>
      </div>

      <div className="metrics-grid metrics-5">
        <MetricCard title={t("device.soilMoisture")} value={reading?.soil_moisture_pct} unit="%" icon={Droplets} color="#239b76" />
        <MetricCard title={t("device.temperature")} value={reading?.temperature} unit="°C" icon={Thermometer} color="#e76f51" />
        <MetricCard title={t("device.humidity")} value={reading?.humidity} unit="%" icon={Wind} color="#3686e8" />
        <MetricCard title={t("device.rainWetness")} value={reading?.rain_wetness_pct} unit="%" icon={CloudRain} color="#6585db" />
        <MetricCard title={t("device.current")} value={reading?.acs_output_voltage_estimate} unit="V" icon={Zap} color="#b26ad9" />
      </div>

      <div className="grid-2 sensor-charts">
        {SENSORS.map((sensor) => (
          <SensorChart key={sensor.key} sensor={sensor} data={history} t={t} />
        ))}
      </div>
    </section>
  );
}
