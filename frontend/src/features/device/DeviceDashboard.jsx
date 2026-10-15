import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";
import api from "../../api";
import { Alert, Badge, EmptyState, PageHeader } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";
import CropPanel from "./CropPanel";
import DecisionHistory from "./DecisionHistory";
import DecisionPanel from "./DecisionPanel";
import LiveReadings from "./LiveReadings";
import PumpPanel from "./PumpPanel";
import WeatherPanel from "./WeatherPanel";

/** Everything about one device. Used by farmers (own devices) and the admin (any device). */
export default function DeviceDashboard({ deviceId, backTo, backLabel }) {
  const { t } = useI18n();
  const [device, setDevice] = useState(null);
  const [weather, setWeather] = useState(null);
  const [decision, setDecision] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [tick, setTick] = useState(0);

  usePolling(
    (isActive) =>
      api
        .get(`/api/devices/${deviceId}`)
        .then((r) => isActive() && setDevice(r.data))
        .catch((err) => isActive() && [403, 404].includes(err.response?.status) && setNotFound(true)),
    15000,
    [deviceId]
  );

  const allowed = device !== null;

  usePolling(
    (isActive) =>
      allowed &&
      Promise.all([api.get(`/api/devices/${deviceId}/weather`), api.get(`/api/devices/${deviceId}/decision`)])
        .then(([w, d]) => {
          if (!isActive()) return;
          setWeather(w.data);
          setDecision(d.data);
        })
        .catch(() => {}),
    30000,
    [deviceId, tick, allowed]
  );

  if (notFound) {
    return <Alert>{t("device.notFound")}</Alert>;
  }
  // Load the panels only once access to this device is confirmed
  if (!allowed) {
    return <EmptyState>{t("common.loading")}</EmptyState>;
  }

  return (
    <div className="device-dashboard">
      <PageHeader
        eyebrow={
          <Link to={backTo} className="back-link">
            <ArrowLeft size={14} /> {backLabel}
          </Link>
        }
        title={device?.name ?? deviceId}
        subtitle={
          <>
            {deviceId}{" "}
            {device && <Badge tone={device.online ? "green" : "red"}>{device.online ? t("common.online") : t("common.offline")}</Badge>}
          </>
        }
        actions={
          <button className="btn btn-ghost" onClick={() => setTick((n) => n + 1)}>
            <RefreshCw size={16} /> {t("common.refresh")}
          </button>
        }
      />

      <LiveReadings deviceId={deviceId} />

      <DecisionPanel decision={decision} />

      <div className="grid-2">
        <PumpPanel deviceId={deviceId} />
        <CropPanel deviceId={deviceId} onSaved={() => setTick((n) => n + 1)} />
      </div>

      <div className="grid-2">
        <WeatherPanel weather={weather} />
        <DecisionHistory deviceId={deviceId} />
      </div>
    </div>
  );
}
