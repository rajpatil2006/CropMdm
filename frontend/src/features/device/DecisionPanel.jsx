import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Brain, Power } from "lucide-react";
import api from "../../api";
import { EmptyState, Panel } from "../../components/ui";
import { useI18n } from "../../i18n/context";
import { formatDateTime } from "../../utils/format";
import { useReasonText } from "./reasonText";

const ACTION_STYLES = {
  IRRIGATE: "action-irrigate",
  WAIT_FOR_RAIN: "action-wait",
  NO_IRRIGATION: "action-none",
  VERIFY: "action-verify",
};
const STAGE_KEYS = ["initial", "development", "mid", "late"];

function useFeatureValue() {
  const { t, locale } = useI18n();
  return (c) => {
    switch (c.feature) {
      case "stage_index":
        return t(`stage.${STAGE_KEYS[Math.round(c.value)]}`);
      case "month":
        return new Date(2026, Math.round(c.value) - 1, 1).toLocaleDateString(locale, { month: "long" });
      case "raining_now":
      case "forecast_available":
        return c.value ? t("value.yes") : t("value.no");
      case "hours_until_rain":
        return c.value >= 72 ? t("value.noneForecast") : c.display_value;
      default:
        return c.display_value;
    }
  };
}

function ModelFacts() {
  const { t } = useI18n();
  const [info, setInfo] = useState(null);

  useEffect(() => {
    let active = true;
    api.get("/api/model/summary").then((r) => active && setInfo(r.data)).catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  if (!info) return null;
  const ev = info.evaluation ?? {};
  const pct = (x) => Math.round((x ?? 0) * 1000) / 10;
  return (
    <div className="model-facts">
      <strong>{t("decision.aboutModel")}</strong>
      <p>
        {t("decision.modelFacts", {
          n: info.replay_decisions?.toLocaleString(),
          farm: info.farm_decisions ? t("decision.modelFarm", { n: info.farm_decisions }) : "",
          acc: pct(ev.model_rain_wait?.accuracy),
          ruleAcc: pct(ev.rule_rain_wait?.accuracy),
          wrong: ev.model_rain_wait?.wrong_wait_crop_stressed,
          ruleWrong: ev.rule_rain_wait?.wrong_wait_crop_stressed,
        })}
      </p>
    </div>
  );
}

export default function DecisionPanel({ decision }) {
  const { t, locale } = useI18n();
  const reasonText = useReasonText();
  const featureValue = useFeatureValue();

  if (!decision) {
    return (
      <Panel title={t("decision.title")}>
        <EmptyState>{t("decision.computing")}</EmptyState>
      </Panel>
    );
  }
  if (decision.status === "no_data") {
    return (
      <Panel title={t("decision.title")}>
        <EmptyState>{t("decision.noData")}</EmptyState>
      </Panel>
    );
  }

  const { rule, model, explanation, state } = decision;
  const actionLabel = t(`action.${decision.action}`);
  const contributions = explanation?.contributions ?? [];
  const bars = contributions.slice(0, 8).map((c) => ({
    name: `${t(`feature.${c.feature}`)} = ${featureValue(c)}`,
    value: Math.round(c.shap * 1000) / 10,
  }));
  const sentences = contributions
    .slice(0, 4)
    .filter((c) => Math.abs(c.shap) >= 0.01)
    .map((c) =>
      t(c.shap > 0 ? "decision.supports" : "decision.against", {
        label: t(`feature.${c.feature}`),
        value: featureValue(c),
        action: actionLabel,
        pts: `${c.shap > 0 ? "+" : ""}${Math.round(c.shap * 100)}`,
      })
    );

  return (
    <Panel
      className="decision-panel"
      title={t("decision.title")}
      subtitle={t("decision.basedOn", { time: formatDateTime(decision.reading_timestamp, locale) })}
      icon={<Power size={21} color="#239b76" />}
    >
      <div className={`action-badge ${ACTION_STYLES[decision.action]}`}>
        <div>
          <span>{t("decision.label")}</span>
          <strong>{actionLabel}</strong>
        </div>
        <div className="action-meta">
          <span>{t("decision.pump", { state: decision.pump_command === "ON" ? t("pump.on") : t("pump.off") })}</span>
          {decision.action === "IRRIGATE" && (
            <span>
              {decision.volume_ml} ml · {decision.pump_seconds} s
            </span>
          )}
        </div>
      </div>

      {decision.pump_state && (decision.action === "IRRIGATE" || decision.pump_state.auto_irrigation) && (
        <p className={`pump-state ${decision.pump_state.auto_irrigation ? "ok" : "wait"}`}>
          {!decision.pump_state.auto_irrigation
            ? t("decision.stateAutoOff")
            : decision.action === "IRRIGATE"
              ? t("decision.statePumpOn")
              : t("decision.statePumpOff")}
        </p>
      )}

      <ul className="reasons">
        {decision.reasons.map((r, i) => (
          <li key={i}>{reasonText(r)}</li>
        ))}
      </ul>

      {rule && (
        <div className="balance-grid">
          <div><span>{t("decision.waterUsed")}</span><strong>{state.depletion_mm} mm</strong></div>
          <div><span>{t("decision.stressAt")}</span><strong>{state.raw_mm} mm</strong></div>
          <div><span>{t("decision.hoursToStress")}</span><strong>{state.hours_to_stress} h</strong></div>
          <div><span>{t("decision.effRain")}</span><strong>{rule.effective_rain_mm} mm</strong></div>
          <div><span>{t("decision.netNeed")}</span><strong>{rule.net_requirement_24h_mm} mm</strong></div>
          <div><span>{t("decision.safeWait")}</span><strong>{state.hours_safe_wait} h</strong></div>
        </div>
      )}

      {model && (
        <div className="xai-block">
          <div className="xai-heading">
            <Brain size={18} color="#7c5cc4" />
            <div>
              <strong>{t("decision.why")}</strong>
              <p>
                {t("decision.aiModel", { action: t(`action.${model.action}`), conf: Math.round(model.confidence * 100) })} ·{" "}
                {decision.decided_by === "model" ? (
                  <span className="good">{t("decision.byModel")}</span>
                ) : (
                  <span className="bad">{t("decision.byGuard")}</span>
                )}{" "}
                · {t("decision.ruleSays", { action: t(`action.${rule.action}`) })}
              </p>
            </div>
          </div>

          <ul className="reasons">
            {sentences.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>

          <ResponsiveContainer width="100%" height={Math.max(180, bars.length * 34)}>
            <BarChart data={bars} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" width={230} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => [`${v > 0 ? "+" : ""}${v}`, t("decision.contribution")]} />
              <ReferenceLine x={0} stroke="#9aa8a0" />
              <Bar dataKey="value" radius={4}>
                {bars.map((b) => (
                  <Cell key={b.name} fill={b.value >= 0 ? "#239b76" : "#e76f51"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="note">
            {t("decision.chartNote", { action: actionLabel, base: Math.round(explanation.base_value * 100) })}
          </p>
          <ModelFacts />
        </div>
      )}
    </Panel>
  );
}
