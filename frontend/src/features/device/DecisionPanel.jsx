import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDownCircle, ArrowUpCircle, Brain, ChevronDown, ChevronUp, Power } from "lucide-react";
import api from "../../api";
import { EmptyState, Panel } from "../../components/ui";
import { useI18n } from "../../i18n/context";
import { cropName, formatDateTime } from "../../utils/format";
import { farmerFact, impactLevel, minutesSeconds } from "./farmerExplain";
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

function SoilWaterBar({ state }) {
  const { t } = useI18n();
  const left = Math.max(0, Math.min(100, Math.round(100 - state.depletion_pct)));
  // Below this much water left, the crop starts to suffer
  const needLine = Math.max(0, Math.min(100, Math.round(100 - (100 * state.raw_mm) / state.taw_mm)));
  const tone = left > needLine ? "ok" : left > needLine / 2 ? "low" : "dry";
  return (
    <div className="soil-water">
      <div className="soil-water-top">
        <span>{t("decision.soilLeft")}</span>
        <strong className={`soil-${tone}`}>{left}%</strong>
      </div>
      <div className="soil-bar" role="img" aria-label={`${t("decision.soilLeft")}: ${left}%`}>
        <div className={`soil-fill soil-fill-${tone}`} style={{ width: `${left}%` }} />
        <div className="soil-line" style={{ left: `${needLine}%` }} />
      </div>
      <p className="soil-caption">{t("decision.soilNeedsBelow", { pct: needLine })}</p>
    </div>
  );
}

export default function DecisionPanel({ decision }) {
  const { t, has, locale } = useI18n();
  const reasonText = useReasonText();
  const featureValue = useFeatureValue();
  const [showDetails, setShowDetails] = useState(false);

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

  // Farmer view: the strongest reasons in plain words
  const crop = state ? cropName(t, has, state.crop, state.crop_name) : "";
  const ctx = {
    crop,
    stageName: (k) => t(`stage.${k}`),
    monthName: (m) => new Date(2026, m - 1, 1).toLocaleDateString(locale, { month: "long" }),
  };
  const simpleReasons = contributions
    .filter((c) => Math.abs(c.shap) >= 0.02)
    .slice(0, 4)
    .map((c) => {
      const fact = farmerFact(c, ctx);
      return { id: c.feature, text: t(fact.key, fact.params), helps: c.shap > 0, level: impactLevel(c.shap) };
    });
  const litres = Math.round((decision.volume_ml ?? 0) / 100) / 10;
  const pumpTime = minutesSeconds(decision.pump_seconds ?? 0);
  const rain48 = state?.forecast_rain_48h_mm ?? 0;

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
            <span>{t("decision.giveWater", { litres, m: pumpTime.m, s: pumpTime.s })}</span>
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

      {model && state && (
        <>
          <SoilWaterBar state={state} />

          <div className="quick-facts">
            <div>
              <span>{t("decision.canWait")}</span>
              <strong>
                {state.hours_safe_wait > 0
                  ? t("decision.hours", { h: Math.round(state.hours_safe_wait) })
                  : t("decision.cannotWait")}
              </strong>
            </div>
            <div>
              <span>{t("decision.rainExpected")}</span>
              <strong>{rain48 > 0 ? `${Math.round(rain48 * 10) / 10} mm` : t("decision.noRain")}</strong>
            </div>
            <div>
              <span>{t("decision.waterToGive")}</span>
              <strong>{decision.action === "IRRIGATE" ? `${litres} L` : "0 L"}</strong>
            </div>
          </div>

          <div className="why-simple">
            <h4>
              <Brain size={18} color="#7c5cc4" /> {t("decision.whySimple")}
            </h4>
            <ul>
              {simpleReasons.map((r) => (
                <li key={r.id} className={r.helps ? "helps" : "against"}>
                  {r.helps ? <ArrowUpCircle size={20} /> : <ArrowDownCircle size={20} />}
                  <span className="why-text">{r.text}</span>
                  <span className={`impact impact-${r.level}`}>{t(`decision.impact.${r.level}`)}</span>
                </li>
              ))}
            </ul>
            <p className="why-legend">
              <span>
                <ArrowUpCircle size={14} /> {t("decision.legendHelps", { action: actionLabel })}
              </span>
              <span>
                <ArrowDownCircle size={14} /> {t("decision.legendAgainst", { action: actionLabel })}
              </span>
            </p>
          </div>
        </>
      )}

      {model && (
        <button className="details-toggle" onClick={() => setShowDetails(!showDetails)} aria-expanded={showDetails}>
          {showDetails ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          {showDetails ? t("decision.hideDetails") : t("decision.showDetails")}
        </button>
      )}

      {model && showDetails && (
        <div className="xai-block">
          <div className="balance-grid">
            <div><span>{t("decision.waterUsed")}</span><strong>{state.depletion_mm} mm</strong></div>
            <div><span>{t("decision.stressAt")}</span><strong>{state.raw_mm} mm</strong></div>
            <div><span>{t("decision.hoursToStress")}</span><strong>{state.hours_to_stress} h</strong></div>
            <div><span>{t("decision.effRain")}</span><strong>{rule.effective_rain_mm} mm</strong></div>
            <div><span>{t("decision.netNeed")}</span><strong>{rule.net_requirement_24h_mm} mm</strong></div>
            <div><span>{t("decision.safeWait")}</span><strong>{state.hours_safe_wait} h</strong></div>
          </div>

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
