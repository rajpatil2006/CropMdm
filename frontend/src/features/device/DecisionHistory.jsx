import { useState } from "react";
import api from "../../api";
import { Badge, EmptyState, Panel } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";
import { formatDateTime } from "../../utils/format";
import { useReasonText } from "./reasonText";

const TONES = { IRRIGATE: "blue", WAIT_FOR_RAIN: "purple", NO_IRRIGATION: "green", VERIFY: "amber" };

export default function DecisionHistory({ deviceId }) {
  const { t, locale } = useI18n();
  const reasonText = useReasonText();
  const [rows, setRows] = useState(null);

  usePolling(
    (isActive) =>
      api
        .get(`/api/devices/${deviceId}/decisions`, { params: { limit: 15 } })
        .then((r) => isActive() && setRows(r.data))
        .catch(() => {}),
    60000,
    [deviceId]
  );

  return (
    <Panel title={t("device.decisionHistory")}>
      {!rows ? (
        <EmptyState>{t("common.loading")}</EmptyState>
      ) : rows.length === 0 ? (
        <EmptyState>{t("decision.noData")}</EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t("device.time")}</th>
                <th>{t("device.decision")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td className="nowrap">{formatDateTime(d.timestamp, locale)}</td>
                  <td>
                    <Badge tone={TONES[d.action]}>{t(`action.${d.action}`)}</Badge>
                  </td>
                  <td className="muted">{d.reasons?.[0] ? reasonText(d.reasons[0]) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
