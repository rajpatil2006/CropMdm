import { useState } from "react";
import { Leaf, Save, Settings2 } from "lucide-react";
import api, { errorMessage } from "../../api";
import { Alert, EmptyState, Panel, Row } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";
import { cropName } from "../../utils/format";

const DEFAULT_CUSTOM_CROP = { name: "", kc_ini: 0.5, kc_mid: 1.05, kc_end: 0.8, stage_days: [20, 30, 40, 20], p: 0.4 };

export default function CropPanel({ deviceId, onSaved }) {
  const { t, has } = useI18n();
  const [catalogue, setCatalogue] = useState(null);
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  // Settings load once (and retry until they do); crop status refreshes every 30 s
  usePolling(
    (isActive) => {
      const requests = [api.get(`/api/devices/${deviceId}/crop-status`)];
      if (!config) requests.push(api.get("/api/crops"), api.get(`/api/devices/${deviceId}/config`));
      return Promise.all(requests)
        .then(([st, cat, cfg]) => {
          if (!isActive()) return;
          setStatus(st.data);
          if (cat) setCatalogue(cat.data);
          if (cfg && !editing) setConfig(cfg.data);
          setMessage(null);
        })
        .catch(() => isActive() && setMessage({ tone: "error", text: t("common.retrying") }));
    },
    config ? 30000 : 8000,
    [deviceId, Boolean(config)]
  );

  const update = (field, value) => setConfig((c) => ({ ...c, [field]: value }));
  const updateCustom = (field, value) => setConfig((c) => ({ ...c, custom_crop: { ...c.custom_crop, [field]: value } }));

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const body = {
        ...config,
        field_capacity_pct: config.field_capacity_pct || null,
        wilting_point_pct: config.wilting_point_pct || null,
      };
      const saved = await api.put(`/api/devices/${deviceId}/config`, body);
      setConfig(saved.data);
      const st = await api.get(`/api/devices/${deviceId}/crop-status`);
      setStatus(st.data);
      setEditing(false);
      setMessage({ tone: "success", text: t("crop.saved") });
      onSaved?.();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err, t("crop.saveFailed")) });
    } finally {
      setSaving(false);
    }
  }

  if (!config || !catalogue) {
    return (
      <Panel title={t("crop.title")}>
        <EmptyState>{message?.text ?? t("common.loading")}</EmptyState>
      </Panel>
    );
  }

  const num = (field) => (e) => update(field, e.target.value === "" ? null : Number(e.target.value));

  return (
    <Panel
      title={t("crop.title")}
      subtitle={t("crop.subtitle")}
      actions={
        <button className="btn btn-ghost btn-sm" onClick={() => setEditing(!editing)}>
          <Settings2 size={15} />
          {editing ? t("common.close") : t("common.edit")}
        </button>
      }
    >
      {editing ? (
        <form className="form-grid" onSubmit={save}>
          <label>
            {t("crop.crop")}
            <select
              value={config.crop}
              onChange={(e) => {
                update("crop", e.target.value);
                if (e.target.value === "custom" && !config.custom_crop) update("custom_crop", { ...DEFAULT_CUSTOM_CROP });
              }}
            >
              {catalogue.crops
                .map((c) => ({ key: c.key, label: cropName(t, has, c.key, c.name) }))
                .sort((a, b) => a.label.localeCompare(b.label))
                .map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              <option value="custom">{t("crop.custom")}</option>
            </select>
          </label>
          <label>
            {t("crop.sowingDate")}
            <input type="date" value={config.sowing_date} onChange={(e) => update("sowing_date", e.target.value)} />
          </label>

          {config.crop === "custom" && config.custom_crop && (
            <fieldset className="custom-crop">
              <legend>{t("crop.customLegend")}</legend>
              <label>
                {t("crop.customName")}
                <input required value={config.custom_crop.name} onChange={(e) => updateCustom("name", e.target.value)} />
              </label>
              {[["kc_ini", "crop.kcIni"], ["kc_mid", "crop.kcMid"], ["kc_end", "crop.kcEnd"], ["p", "crop.p"]].map(([key, label]) => (
                <label key={key}>
                  {t(label)}
                  <input type="number" step="0.01" value={config.custom_crop[key]}
                    onChange={(e) => updateCustom(key, Number(e.target.value))} />
                </label>
              ))}
              <label className="wide">
                {t("crop.stageDays")}
                <input
                  value={config.custom_crop.stage_days.join(", ")}
                  onChange={(e) => updateCustom("stage_days", e.target.value.split(",").map((v) => Number(v.trim()) || 0))}
                />
              </label>
            </fieldset>
          )}

          <label>
            {t("crop.soilType")}
            <select value={config.soil_type} onChange={(e) => update("soil_type", e.target.value)}>
              {catalogue.soils.map((s) => (
                <option key={s.key} value={s.key}>{t(`soil.${s.key}`)}</option>
              ))}
            </select>
          </label>
          <label>
            {t("crop.rootDepth")}
            <input type="number" value={config.root_depth_mm} onChange={num("root_depth_mm")} />
          </label>
          <label>
            {t("crop.fcOverride")}
            <input type="number" step="0.1" placeholder={t("crop.fromSoil")} value={config.field_capacity_pct ?? ""}
              onChange={num("field_capacity_pct")} />
          </label>
          <label>
            {t("crop.wpOverride")}
            <input type="number" step="0.1" placeholder={t("crop.fromSoil")} value={config.wilting_point_pct ?? ""}
              onChange={num("wilting_point_pct")} />
          </label>
          <label>
            {t("crop.potArea")}
            <input type="number" value={config.pot_area_cm2} onChange={num("pot_area_cm2")} />
          </label>
          <label>
            {t("crop.pumpFlow")}
            <input type="number" value={config.pump_flow_ml_per_min} onChange={num("pump_flow_ml_per_min")} />
          </label>
          <label>
            {t("crop.latitude")}
            <input type="number" step="0.0001" value={config.latitude} onChange={num("latitude")} />
          </label>
          <label>
            {t("crop.longitude")}
            <input type="number" step="0.0001" value={config.longitude} onChange={num("longitude")} />
          </label>
          <label>
            {t("crop.rainThreshold")}
            <input type="number" value={config.rain_probability_threshold} onChange={num("rain_probability_threshold")} />
          </label>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={saving}>
              <Save size={16} /> {saving ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </form>
      ) : (
        status && (
          <>
            <div className="stage-banner">
              <Leaf size={20} />
              <div>
                <strong>{cropName(t, has, status.crop, status.crop_name)}</strong> ·{" "}
                {t("crop.stageLine", { stage: t(`stage.${status.stage}`) })}
                <p>
                  {t("crop.dayOf", { day: status.days_after_sowing, total: status.season_length_days })}
                  {status.season_complete ? ` (${t("crop.seasonComplete")})` : ""}
                </p>
              </div>
            </div>
            <Row label={t("crop.soilType")} value={t(`soil.${status.soil_type}`)} />
            <Row label={t("crop.kc")} value={status.kc} />
            <Row label={t("crop.etc")} value={`${status.etc_mm_day} mm/day`} />
            <Row label={t("crop.taw")} value={`${status.taw_mm} mm`} />
            <Row label={t("crop.raw")} value={`${status.raw_mm} mm`} />
            <Row label={t("crop.preferred")}
              value={`${status.preferred_moisture_min_pct}–${status.preferred_moisture_max_pct}%`} />
          </>
        )
      )}
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
    </Panel>
  );
}
