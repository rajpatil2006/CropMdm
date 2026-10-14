import { Link } from "react-router-dom";
import { ChevronRight, Droplets, Sprout, Thermometer } from "lucide-react";
import { useI18n } from "../i18n/context";
import { cropName, formatAgo } from "../utils/format";
import { Badge } from "./ui";

const TONES = { IRRIGATE: "blue", WAIT_FOR_RAIN: "purple", NO_IRRIGATION: "green", VERIFY: "amber" };

export default function DeviceCard({ device, to }) {
  const { t, has } = useI18n();
  return (
    <Link to={to} className="device-card">
      <div className="device-card-top">
        <div className="device-icon">
          <Sprout size={20} />
        </div>
        <div>
          <strong>{device.name}</strong>
          <span>{cropName(t, has, device.crop, device.crop)} · {device.device_id}</span>
        </div>
        <Badge tone={device.online ? "green" : "red"}>{device.online ? t("common.online") : t("common.offline")}</Badge>
      </div>
      <div className="device-card-metrics">
        <span>
          <Droplets size={15} /> {device.soil_moisture_pct ?? "--"}%
        </span>
        <span>
          <Thermometer size={15} /> {device.temperature ?? "--"}°C
        </span>
        <span className="muted">
          {t("farmer.lastSeen")}: {formatAgo(t, device.seconds_since_seen)}
        </span>
      </div>
      <div className="device-card-bottom">
        {device.last_action ? (
          <Badge tone={TONES[device.last_action]}>{t(`action.${device.last_action}`)}</Badge>
        ) : (
          <span className="muted">--</span>
        )}
        <span className="muted">{device.auto_irrigation ? t("farmer.autoOn") : t("farmer.autoOff")}</span>
        <ChevronRight size={18} />
      </div>
    </Link>
  );
}
