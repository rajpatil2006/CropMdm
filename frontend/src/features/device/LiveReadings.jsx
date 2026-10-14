import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, CloudRain, Droplets, Thermometer, Wind } from "lucide-react";
import api from "../../api";
import { EmptyState, MetricCard, Panel } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";
import { formatDateTime } from "../../utils/format";

export default function LiveReadings({ deviceId }) {
  const { t, locale } = useI18n();
  const [reading, setReading] = useState(null);
  const [history, setHistory] = useState([]);

  usePolling(
    (isActive) =>
      Promise.all([
        api.get(`/api/devices/${deviceId}/readings/latest`),
        api.get(`/api/devices/${deviceId}/readings`, { params: { limit: 60 } }),
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
                soil: r.soil_moisture_pct,
                temperature: r.temperature,
              }))
          );
        })
        .catch(() => {}),
    5000,
    [deviceId, locale]
  );

  return (
    <>
      <div className="section-heading">
        <h3>{t("device.liveReadings")}</h3>
        <span className="last-updated">
          {reading ? t("device.lastRecord", { time: formatDateTime(reading.timestamp, locale) }) : t("device.waiting")}
        </span>
      </div>

      <div className="metrics-grid">
        <MetricCard title={t("device.soilMoisture")} value={reading?.soil_moisture_pct} unit="%" icon={Droplets} color="#239b76" />
        <MetricCard title={t("device.temperature")} value={reading?.temperature} unit="°C" icon={Thermometer} color="#e76f51" />
        <MetricCard title={t("device.humidity")} value={reading?.humidity} unit="%" icon={Wind} color="#3686e8" />
        <MetricCard title={t("device.rainWetness")} value={reading?.rain_wetness_pct} unit="%" icon={CloudRain} color="#6585db" />
      </div>

      <Panel title={t("device.history")} subtitle={t("device.historySubtitle")} icon={<Activity size={20} color="#239b76" />}>
        {history.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e6ece7" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} minTickGap={30} />
              <YAxis yAxisId="soil" unit="%" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="temp" orientation="right" unit="°" tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line yAxisId="soil" type="monotone" dataKey="soil" name={t("device.soilMoisture")}
                stroke="#239b76" strokeWidth={2} dot={false} />
              <Line yAxisId="temp" type="monotone" dataKey="temperature" name={t("device.temperature")}
                stroke="#e76f51" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState>{t("device.noHistory")}</EmptyState>
        )}
      </Panel>
    </>
  );
}
