import { useState } from "react";
import { Power } from "lucide-react";
import api, { errorMessage } from "../../api";
import { Alert, EmptyState, Panel, Row } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";
import { formatAgo, formatTime } from "../../utils/format";

const BY = { ai: "pump.byAi", farmer: "pump.byFarmer", admin: "pump.byAdmin" };

export default function PumpPanel({ deviceId }) {
  const { t, locale } = useI18n();
  const [status, setStatus] = useState(null);
  const [seconds, setSeconds] = useState(30);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  function load(isActive = () => true) {
    return api
      .get(`/api/devices/${deviceId}/pump`)
      .then((r) => isActive() && setStatus(r.data))
      .catch(() => {});
  }
  usePolling(load, 4000, [deviceId]);

  async function send(action) {
    setBusy(true);
    setMessage(null);
    try {
      await api.post(`/api/devices/${deviceId}/pump/command`, { action, seconds: action === "ON" ? Number(seconds) : 0 });
      setMessage({ tone: "success", text: action === "ON" ? t("pump.queuedOn", { s: seconds }) : t("pump.queuedOff") });
      load();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err, t("common.error")) });
    } finally {
      setBusy(false);
    }
  }

  async function toggleSensorChecks() {
    try {
      await api.put(`/api/devices/${deviceId}/sensor-checks`, null, { params: { enabled: !status.sensor_checks } });
      load();
    } catch {
      setMessage({ tone: "error", text: t("pump.sensorChecksFailed") });
    }
  }

  async function toggleAuto() {
    try {
      await api.put(`/api/devices/${deviceId}/pump/auto`, null, { params: { enabled: !status.auto_irrigation } });
      load();
    } catch {
      setMessage({ tone: "error", text: t("pump.autoFailed") });
    }
  }

  if (!status) {
    return (
      <Panel title={t("pump.title")}>
        <EmptyState>{t("common.loading")}</EmptyState>
      </Panel>
    );
  }

  const ready = status.device_online;
  const ago = formatAgo(t, status.seconds_since_contact);

  return (
    <Panel
      className="pump-panel"
      title={t("pump.title")}
      subtitle={t("pump.subtitle")}
      icon={<Power size={21} color={ready ? "#239b76" : "#9aa8a0"} />}
    >
      <Row
        label={t("pump.device")}
        value={
          status.seconds_since_contact == null ? (
            t("pump.neverSeen")
          ) : ready ? (
            <span className="good">{t("pump.onlineAgo", { ago })}</span>
          ) : (
            <span className="bad">{t("pump.offlineAgo", { ago })}</span>
          )
        }
      />
      <div className="status-row">
        <span>{t("pump.auto")}</span>
        <button className={`toggle ${status.auto_irrigation ? "toggle-on" : ""}`} onClick={toggleAuto}
          aria-pressed={status.auto_irrigation}>
          {status.auto_irrigation ? t("pump.on") : t("pump.off")}
        </button>
      </div>
      <div className="status-row">
        <span>{t("pump.sensorChecks")}</span>
        <button className={`toggle ${status.sensor_checks ? "toggle-on" : "toggle-warn"}`} onClick={toggleSensorChecks}
          aria-pressed={status.sensor_checks}>
          {status.sensor_checks ? t("pump.on") : t("pump.off")}
        </button>
      </div>
      {!status.sensor_checks && <Alert tone="warning">{t("pump.sensorChecksOff")}</Alert>}

      <div className="pump-buttons">
        <label>
          {t("pump.runFor")}
          <input type="number" min="1" max="600" value={seconds} onChange={(e) => setSeconds(e.target.value)} />
        </label>
        <button className="btn btn-blue" disabled={!ready || busy || status.auto_irrigation} onClick={() => send("ON")}>
          {t("pump.pumpOn")}
        </button>
        <button className="btn btn-danger" disabled={!ready || busy || status.auto_irrigation} onClick={() => send("OFF")}>
          {t("pump.pumpOff")}
        </button>
      </div>
      {status.auto_irrigation && <p className="note">{t("pump.autoControls")}</p>}
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {!ready && <p className="note">{t("pump.offlineNote")}</p>}

      {status.recent_commands.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t("pump.time")}</th>
                <th>{t("pump.command")}</th>
                <th>{t("pump.by")}</th>
                <th>{t("pump.status")}</th>
              </tr>
            </thead>
            <tbody>
              {status.recent_commands.map((c) => (
                <tr key={c.id}>
                  <td>{formatTime(c.created_at, locale)}</td>
                  <td>
                    {c.action === "ON" ? `${t("pump.on")} ${c.seconds}s` : t("pump.off")}
                  </td>
                  <td>{t(BY[c.source] ?? "pump.byFarmer")}</td>
                  <td title={c.ack_detail ?? ""}>{t(`pump.st.${c.status}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
