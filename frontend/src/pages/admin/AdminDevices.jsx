import { useState } from "react";
import { Link } from "react-router-dom";
import { Copy, KeyRound, Plus } from "lucide-react";
import api, { errorMessage } from "../../api";
import { Alert, Badge, EmptyState, PageHeader, Panel } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";
import { formatAgo } from "../../utils/format";

function KeyNotice({ deviceId, deviceKey, onClose }) {
  const snippet = `#define DEVICE_ID   "${deviceId}"\n#define DEVICE_KEY  "${deviceKey}"`;
  return (
    <Alert tone="info">
      <div className="key-notice">
        <strong><KeyRound size={16} /> Device key for {deviceId} — shown only once</strong>
        <p>Put these two lines in the ESP32's <code>secrets.h</code> and upload the firmware.</p>
        <pre>{snippet}</pre>
        <div className="row-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard?.writeText(snippet)}>
            <Copy size={14} /> Copy
          </button>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Done</button>
        </div>
      </div>
    </Alert>
  );
}

export default function AdminDevices() {
  const { t } = useI18n();
  const [devices, setDevices] = useState(null);
  const [farmers, setFarmers] = useState([]);
  const [unregistered, setUnregistered] = useState([]);
  const [form, setForm] = useState({ device_id: "", name: "", owner: "" });
  const [issuedKey, setIssuedKey] = useState(null);
  const [message, setMessage] = useState(null);
  const [reload, setReload] = useState(0);

  usePolling(
    (isActive) =>
      Promise.all([
        api.get("/api/admin/devices"),
        api.get("/api/admin/users", { params: { status: "active" } }),
        api.get("/api/admin/unregistered-devices"),
      ])
        .then(([d, u, un]) => {
          if (!isActive()) return;
          setDevices(d.data);
          setFarmers(u.data.filter((x) => x.role === "farmer"));
          setUnregistered(un.data);
        })
        .catch(() => isActive() && setMessage({ tone: "error", text: "Could not load devices." })),
    15000,
    [reload]
  );

  async function register(event) {
    event.preventDefault();
    try {
      const r = await api.post("/api/admin/devices", { ...form, owner: form.owner || null });
      setIssuedKey({ deviceId: r.data.device_id, key: r.data.device_key });
      setForm({ device_id: "", name: "", owner: "" });
      setMessage(null);
      setReload((n) => n + 1);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  async function assign(deviceId, owner) {
    try {
      await api.patch(`/api/admin/devices/${deviceId}`, owner ? { owner } : { unassign: true });
      setReload((n) => n + 1);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  async function newKey(deviceId) {
    if (!window.confirm(`Create a new key for ${deviceId}? The ESP32 stops working until its firmware has the new key.`)) return;
    try {
      const r = await api.post(`/api/admin/devices/${deviceId}/key`);
      setIssuedKey({ deviceId, key: r.data.device_key });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  async function remove(deviceId) {
    if (!window.confirm(`Unregister ${deviceId}? Its readings are kept, but it can no longer upload.`)) return;
    try {
      await api.delete(`/api/admin/devices/${deviceId}`);
      setReload((n) => n + 1);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <>
      <PageHeader eyebrow="Admin console" title="Devices"
        subtitle="Register ESP32 devices, give each one a secret key and assign it to a farmer." />
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {issuedKey && <KeyNotice deviceId={issuedKey.deviceId} deviceKey={issuedKey.key} onClose={() => setIssuedKey(null)} />}

      <Panel title="Register a device" subtitle="One farmer can own several devices (fields or pots).">
        <form className="form-grid" onSubmit={register}>
          <label>
            Device ID
            <input required pattern="[A-Za-z0-9_\-]{3,40}" placeholder="ESP32_FARM_02" value={form.device_id}
              onChange={(e) => setForm({ ...form, device_id: e.target.value })} />
            {unregistered.length > 0 && (
              <small>
                Sending data but not registered:{" "}
                {unregistered.map((id) => (
                  <button type="button" key={id} className="link-button" onClick={() => setForm({ ...form, device_id: id })}>{id}</button>
                ))}
              </small>
            )}
          </label>
          <label>
            Name
            <input required placeholder="Tomato pot A" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label>
            Farmer
            <select value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })}>
              <option value="">Unassigned</option>
              {farmers.map((f) => (
                <option key={f.username} value={f.username}>{f.name} ({f.username})</option>
              ))}
            </select>
          </label>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit"><Plus size={16} /> Register device</button>
          </div>
        </form>
      </Panel>

      <Panel title="Registered devices">
        {!devices ? (
          <EmptyState>Loading…</EmptyState>
        ) : devices.length === 0 ? (
          <EmptyState>No devices yet.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Device</th><th>Status</th><th>Farmer</th><th>Crop</th><th>Soil</th><th>Last decision</th><th /></tr>
              </thead>
              <tbody>
                {devices.map((d) => (
                  <tr key={d.device_id}>
                    <td>
                      <Link to={`/admin/devices/${d.device_id}`}><strong>{d.name}</strong></Link>
                      <div className="muted small">{d.device_id}</div>
                    </td>
                    <td>
                      <Badge tone={d.online ? "green" : "red"}>{d.online ? "online" : "offline"}</Badge>
                      <div className="muted small">{formatAgo(t, d.seconds_since_seen)}</div>
                    </td>
                    <td>
                      <select value={d.owner ?? ""} onChange={(e) => assign(d.device_id, e.target.value)}>
                        <option value="">Unassigned</option>
                        {farmers.map((f) => (
                          <option key={f.username} value={f.username}>{f.name} ({f.username})</option>
                        ))}
                      </select>
                    </td>
                    <td>{d.crop}</td>
                    <td>{d.soil_moisture_pct ?? "--"}%</td>
                    <td>{d.last_action ?? "--"}</td>
                    <td className="row-actions">
                      <Link className="btn btn-ghost btn-sm" to={`/admin/devices/${d.device_id}`}>Open</Link>
                      <button className="btn btn-ghost btn-sm" onClick={() => newKey(d.device_id)}>New key</button>
                      <button className="btn btn-ghost btn-sm danger" onClick={() => remove(d.device_id)}>Remove</button>
                    </td>
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
