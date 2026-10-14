import { useState } from "react";
import api, { errorMessage } from "../../api";
import { Alert, Badge, EmptyState, PageHeader, Panel } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { formatDateTime } from "../../utils/format";

const STATUS_TONE = { active: "green", pending: "amber", rejected: "red", disabled: "neutral" };
const FILTERS = ["all", "pending", "active", "disabled", "rejected"];
const LANGS = { en: "English", mr: "मराठी", hi: "हिन्दी" };

export default function AdminFarmers() {
  const [users, setUsers] = useState(null);
  const [filter, setFilter] = useState("all");
  const [message, setMessage] = useState(null);
  const [reload, setReload] = useState(0);

  usePolling(
    (isActive) =>
      api
        .get("/api/admin/users", { params: filter === "all" ? {} : { status: filter } })
        .then((r) => isActive() && setUsers(r.data))
        .catch(() => isActive() && setMessage({ tone: "error", text: "Could not load accounts." })),
    20000,
    [filter, reload]
  );

  async function act(username, action) {
    if (["reject", "disable"].includes(action) && !window.confirm(`${action} ${username}?`)) return;
    try {
      const r = await api.post(`/api/admin/users/${username}/${action}`);
      setMessage(
        r.data.temporary_password
          ? { tone: "info", text: `Temporary password for ${username}: ${r.data.temporary_password} — share it privately; it is shown only once.` }
          : { tone: "success", text: `${username}: ${r.data.status}` }
      );
      setReload((n) => n + 1);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  const pending = (users ?? []).filter((u) => u.status === "pending");

  return (
    <>
      <PageHeader eyebrow="Admin console" title="Farmers" subtitle="Approve sign-ups, manage accounts and reset passwords." />
      {message && <Alert tone={message.tone}>{message.text}</Alert>}

      {filter === "all" && pending.length > 0 && (
        <Panel title={`Waiting for approval (${pending.length})`} className="highlight-panel">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Username</th><th>Village</th><th>Phone</th><th>Signed up</th><th /></tr>
              </thead>
              <tbody>
                {pending.map((u) => (
                  <tr key={u.username}>
                    <td>{u.name}</td>
                    <td>{u.username}</td>
                    <td>{u.village || "--"}</td>
                    <td>{u.phone || "--"}</td>
                    <td className="nowrap">{formatDateTime(u.created_at)}</td>
                    <td className="row-actions">
                      <button className="btn btn-primary btn-sm" onClick={() => act(u.username, "approve")}>Approve</button>
                      <button className="btn btn-ghost btn-sm" onClick={() => act(u.username, "reject")}>Reject</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Panel
        title="All accounts"
        actions={
          <div className="segmented">
            {FILTERS.map((f) => (
              <button key={f} className={filter === f ? "active" : ""} onClick={() => setFilter(f)}>{f}</button>
            ))}
          </div>
        }
      >
        {!users ? (
          <EmptyState>Loading…</EmptyState>
        ) : users.length === 0 ? (
          <EmptyState>No accounts.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th>Devices</th><th>Language</th><th>Last login</th><th /></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.username}>
                    <td>{u.name}<div className="muted small">{u.village}</div></td>
                    <td>{u.username}</td>
                    <td>{u.role}</td>
                    <td><Badge tone={STATUS_TONE[u.status]}>{u.status}</Badge></td>
                    <td>{u.devices.length ? u.devices.join(", ") : "--"}</td>
                    <td>{LANGS[u.language] ?? "--"}</td>
                    <td className="nowrap">{formatDateTime(u.last_login)}</td>
                    <td className="row-actions">
                      {u.status === "pending" && <button className="btn btn-primary btn-sm" onClick={() => act(u.username, "approve")}>Approve</button>}
                      {u.status === "active" && u.role !== "admin" && <button className="btn btn-ghost btn-sm" onClick={() => act(u.username, "disable")}>Disable</button>}
                      {["disabled", "rejected"].includes(u.status) && <button className="btn btn-ghost btn-sm" onClick={() => act(u.username, "enable")}>Enable</button>}
                      {u.status !== "pending" && <button className="btn btn-ghost btn-sm" onClick={() => act(u.username, "reset-password")}>Reset password</button>}
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
