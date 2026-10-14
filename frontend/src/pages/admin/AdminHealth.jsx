import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../../api";
import { Alert, Badge, EmptyState, PageHeader, Panel, Row } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { formatDateTime } from "../../utils/format";

const ACTION_LABELS = {
  login: "Logged in",
  register: "Signed up",
  change_password: "Changed password",
  user_approve: "Approved farmer",
  user_reject: "Rejected farmer",
  user_disable: "Disabled account",
  user_enable: "Enabled account",
  user_reset_password: "Reset password",
  device_register: "Registered device",
  device_update: "Updated device",
  device_new_key: "New device key",
  device_remove: "Removed device",
  pump_command: "Pump command",
  auto_irrigation: "Auto-irrigation",
  sensor_checks: "Sensor fault check",
  ai_resume: "Ended AI pause",
  ai_pause: "Pause after watering",
  update_crop_settings: "Changed crop settings",
  label_farm_data: "Labelled farm data",
  model_retrain: "Started retraining",
};

function details(entry) {
  const d = entry.details ?? {};
  if (entry.action === "pump_command") return `${d.action}${d.action === "ON" ? ` ${d.seconds}s` : ""}`;
  if (["auto_irrigation", "sensor_checks", "ai_pause"].includes(entry.action)) return d.enabled ? "turned on" : "turned off";
  if (entry.action === "update_crop_settings") return `${d.crop}, ${d.soil}, sown ${d.sowing_date}`;
  return Object.entries(d).map(([k, v]) => `${k}: ${v}`).join(", ");
}

export default function AdminHealth() {
  const [health, setHealth] = useState(null);
  const [audit, setAudit] = useState(null);
  const [actor, setActor] = useState("");
  const [error, setError] = useState("");

  usePolling(
    (isActive) =>
      Promise.all([
        api.get("/api/admin/health"),
        api.get("/api/admin/audit", { params: { limit: 150, ...(actor ? { actor } : {}) } }),
      ])
        .then(([h, a]) => {
          if (!isActive()) return;
          setHealth(h.data);
          setAudit(a.data);
          setError("");
        })
        .catch(() => isActive() && setError("Could not load system health.")),
    20000,
    [actor]
  );

  return (
    <>
      <PageHeader eyebrow="Admin console" title="Health & logs" subtitle="System status, failed pump commands and the audit trail." />
      <Alert>{error}</Alert>
      {!health ? (
        <EmptyState>Loading…</EmptyState>
      ) : (
        <>
          <div className="grid-2">
            <Panel title="System">
              <Row label="Database" value={<Badge tone={health.database === "connected" ? "green" : "red"}>{health.database}</Badge>} />
              <Row label="AI model trained" value={formatDateTime(health.model.trained_at)} />
              <Row label="Retraining" value={health.model.retrain?.state ?? "idle"} />
              <Row label="Farmers waiting for approval" value={health.farmers_pending} />
              {health.forecast_cache.map((f) => (
                <Row key={f.location} label={`Forecast ${f.location}`}
                  value={<Badge tone={f.age_hours <= 3 ? "green" : f.age_hours <= 12 ? "amber" : "red"}>{f.age_hours} h old</Badge>} />
              ))}
            </Panel>

            <Panel title={`Offline devices (${health.devices_offline.length})`}>
              {health.devices_offline.length === 0 ? (
                <EmptyState>All devices are online.</EmptyState>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>Device</th><th>Farmer</th><th>Last seen</th></tr></thead>
                    <tbody>
                      {health.devices_offline.map((d) => (
                        <tr key={d.device_id}>
                          <td><Link to={`/admin/devices/${d.device_id}`}>{d.name}</Link><div className="muted small">{d.device_id}</div></td>
                          <td>{d.owner ?? "--"}</td>
                          <td className="nowrap">{formatDateTime(d.last_seen)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>

          <Panel title={`Problem pump commands, last 7 days (${health.problem_commands.length})`}
            subtitle="Expired, unanswered or rejected commands usually mean a device was offline or misconfigured.">
            {health.problem_commands.length === 0 ? (
              <EmptyState>No problems.</EmptyState>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Time</th><th>Device</th><th>Command</th><th>By</th><th>Status</th><th>Detail</th></tr></thead>
                  <tbody>
                    {health.problem_commands.map((c) => (
                      <tr key={c.id}>
                        <td className="nowrap">{formatDateTime(c.created_at)}</td>
                        <td>{c.device_id}</td>
                        <td>{c.action}</td>
                        <td>{c.source}</td>
                        <td><Badge tone="red">{c.status}</Badge></td>
                        <td className="muted">{c.detail ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}

      <Panel
        title="Audit log"
        subtitle="Who did what, and when."
        actions={
          <input className="input-sm" placeholder="Filter by username" value={actor}
            onChange={(e) => setActor(e.target.value.trim().toLowerCase())} />
        }
      >
        {!audit ? (
          <EmptyState>Loading…</EmptyState>
        ) : audit.length === 0 ? (
          <EmptyState>No entries.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
              <tbody>
                {audit.map((e) => (
                  <tr key={e.id}>
                    <td className="nowrap">{formatDateTime(e.at)}</td>
                    <td>{e.actor} <span className="muted small">{e.role}</span></td>
                    <td>{ACTION_LABELS[e.action] ?? e.action}</td>
                    <td>{e.target ?? ""}</td>
                    <td className="muted">{details(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
