import { useState } from "react";
import { Link } from "react-router-dom";
import { UserCheck } from "lucide-react";
import api from "../../api";
import DeviceCard from "../../components/DeviceCard";
import { Alert, EmptyState, PageHeader, Panel, StatCard } from "../../components/ui";
import usePolling from "../../hooks/usePolling";

const ACTIONS = [
  ["IRRIGATE", "Irrigate"],
  ["WAIT_FOR_RAIN", "Wait for rain"],
  ["NO_IRRIGATION", "No irrigation"],
  ["VERIFY", "Verify"],
];

export default function AdminOverview() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  usePolling(
    (isActive) =>
      api
        .get("/api/admin/overview")
        .then((r) => {
          if (!isActive()) return;
          setData(r.data);
          setError("");
        })
        .catch(() => isActive() && setError("Could not load the overview. Retrying…")),
    15000,
    []
  );

  return (
    <>
      <PageHeader eyebrow="Admin console" title="All farms overview" subtitle="Live status of every farmer and device." />
      <Alert>{error}</Alert>
      {!data ? (
        <EmptyState>Loading…</EmptyState>
      ) : (
        <>
          {data.farmers_pending > 0 && (
            <Alert tone="info">
              <UserCheck size={16} /> {data.farmers_pending} farmer{data.farmers_pending > 1 ? "s are" : " is"} waiting
              for approval. <Link to="/admin/farmers">Review now</Link>
            </Alert>
          )}
          <div className="stat-grid">
            <StatCard label="Active farmers" value={data.farmers_active} />
            <StatCard label="Pending approvals" value={data.farmers_pending} tone={data.farmers_pending ? "amber" : undefined} />
            <StatCard label="Devices online" value={`${data.devices_online} / ${data.devices_total}`}
              tone={data.devices_online < data.devices_total ? "red" : "green"} />
            <StatCard label="Unassigned devices" value={data.devices_unassigned} />
            <StatCard label="Pump commands (24 h)" value={data.pump_commands_24h} />
          </div>

          <Panel title="Decisions in the last 24 h" subtitle="One decision is logged per new sensor reading.">
            <div className="stat-grid compact">
              {ACTIONS.map(([key, label]) => (
                <StatCard key={key} label={label} value={data.decisions_24h[key] ?? 0} />
              ))}
            </div>
          </Panel>

          <div className="section-heading">
            <h3>Devices</h3>
            <Link to="/admin/devices">Manage devices</Link>
          </div>
          {data.devices.length === 0 ? (
            <div className="panel">
              <EmptyState>No devices registered yet. Add one under Devices.</EmptyState>
            </div>
          ) : (
            <div className="card-grid">
              {data.devices.map((d) => (
                <DeviceCard key={d.device_id} device={d} to={`/admin/devices/${d.device_id}`} />
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
