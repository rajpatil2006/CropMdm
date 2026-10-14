import { useState } from "react";
import { BrainCircuit, RefreshCw, Tags } from "lucide-react";
import api, { errorMessage } from "../../api";
import { Alert, Badge, EmptyState, PageHeader, Panel, Row, StatCard } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { formatDateTime } from "../../utils/format";

const pct = (x) => (x == null ? "--" : `${Math.round(x * 1000) / 10}%`);

export default function AdminModel() {
  const [model, setModel] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  const running = model?.retrain?.state === "running";

  usePolling(
    (isActive) =>
      api
        .get("/api/admin/model")
        .then((r) => isActive() && setModel(r.data))
        .catch(() => isActive() && setMessage({ tone: "error", text: "Could not load model details." })),
    running ? 5000 : 30000,
    [reload, running]
  );

  async function labelFarmData() {
    setBusy(true);
    try {
      const r = await api.post("/api/admin/model/label-farm-data");
      setMessage({ tone: "success", text: `Labelled ${r.data.labelled} new farm decisions (${r.data.skipped} skipped). Total farm labels: ${r.data.total_farm_labels}.` });
      setReload((n) => n + 1);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  async function retrain() {
    if (!window.confirm("Retrain the AI model now? It takes a few minutes; decisions keep using the current model until it finishes.")) return;
    try {
      await api.post("/api/admin/model/retrain");
      setMessage({ tone: "info", text: "Retraining started." });
      setReload((n) => n + 1);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  if (!model) {
    return (
      <>
        <PageHeader eyebrow="Admin console" title="AI model" />
        {message ? <Alert tone={message.tone}>{message.text}</Alert> : <EmptyState>Loading…</EmptyState>}
      </>
    );
  }

  const ev = model.evaluation ?? {};
  const m = ev.model_rain_wait ?? {};
  const r = ev.rule_rain_wait ?? {};
  const retrain_state = model.retrain ?? {};

  return (
    <>
      <PageHeader
        eyebrow="Admin console"
        title="AI model"
        subtitle="Random Forest irrigation model with SHAP explanations."
        actions={
          <>
            <button className="btn btn-ghost" onClick={labelFarmData} disabled={busy}><Tags size={16} /> Label farm data</button>
            <button className="btn btn-primary" onClick={retrain} disabled={running}>
              <RefreshCw size={16} className={running ? "spin" : ""} /> {running ? "Retraining…" : "Retrain model"}
            </button>
          </>
        }
      />
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {retrain_state.state === "failed" && <Alert>Last retraining failed: {retrain_state.error}</Alert>}
      {retrain_state.state === "done" && (
        <Alert tone="success">Retrained at {formatDateTime(retrain_state.finished_at)} using {retrain_state.farm_decisions} farm decisions.</Alert>
      )}

      <div className="stat-grid">
        <StatCard label="Replay decisions (real weather)" value={model.replay_decisions?.toLocaleString()} />
        <StatCard label="Farm decisions in model" value={model.farm_decisions ?? 0} />
        <StatCard label="Farm labels available" value={model.farm_labels} />
        <StatCard label="Decisions logged" value={model.decisions_logged?.toLocaleString()} />
      </div>

      <div className="grid-2">
        <Panel title="Training" icon={<BrainCircuit size={20} color="#7c5cc4" />}>
          <Row label="Trained at" value={formatDateTime(model.trained_at)} />
          <Row label="Features" value={model.features?.length} />
          <Row label="Classes" value={model.classes?.join(", ")} />
          <p className="note">{model.trained_on}.</p>
          <p className="note">
            Farm labels come from decisions older than 48 h, judged by what the soil sensor and real rainfall showed
            afterwards. Label them, then retrain to include them (each counts 20× a replayed decision).
          </p>
        </Panel>

        <Panel title="Held-out evaluation" subtitle={`Cities never seen in training: ${ev.holdout_locations?.join(", ") ?? "--"}`}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Decisions where the crop needed water</th><th>AI model</th><th>Forecast-only rule</th></tr>
              </thead>
              <tbody>
                <tr><td>Correct</td><td><strong>{pct(m.accuracy)}</strong></td><td>{pct(r.accuracy)}</td></tr>
                <tr><td>Wrong waits (crop stressed)</td><td><strong>{m.wrong_wait_crop_stressed}</strong></td><td>{r.wrong_wait_crop_stressed}</td></tr>
                <tr><td>Correct waits</td><td><strong>{m.correct_waits}</strong></td><td>{r.correct_waits}</td></tr>
                <tr><td>Irrigated although rain came</td><td><strong>{m.unneeded_irrigation_rain_came}</strong></td><td>{r.unneeded_irrigation_rain_came}</td></tr>
              </tbody>
            </table>
          </div>
          <p className="note">
            Overall accuracy: model {pct(ev.model_accuracy)} vs rule {pct(ev.rule_accuracy)} on {ev.test_decisions?.toLocaleString()} decisions
            (inflated by easy moist-soil cases — the table above is the meaningful comparison).
          </p>
          {retrain_state.state && retrain_state.state !== "idle" && (
            <p>Retraining: <Badge tone={{ running: "amber", done: "green", failed: "red" }[retrain_state.state]}>{retrain_state.state}</Badge></p>
          )}
        </Panel>
      </div>
    </>
  );
}
