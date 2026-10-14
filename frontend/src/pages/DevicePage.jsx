import { useParams } from "react-router-dom";
import { useAuth } from "../auth/context";
import DeviceDashboard from "../features/device/DeviceDashboard";
import { useI18n } from "../i18n/context";

export default function DevicePage() {
  const { deviceId } = useParams();
  const { user } = useAuth();
  const { t } = useI18n();
  const admin = user.role === "admin";
  return (
    <DeviceDashboard
      key={deviceId}
      deviceId={deviceId}
      backTo={admin ? "/admin/devices" : "/farm"}
      backLabel={admin ? "All devices" : t("nav.myFarms")}
    />
  );
}
