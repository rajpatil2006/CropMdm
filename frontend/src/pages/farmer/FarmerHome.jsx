import { useState } from "react";
import api from "../../api";
import { useAuth } from "../../auth/context";
import DeviceCard from "../../components/DeviceCard";
import { Alert, EmptyState, PageHeader } from "../../components/ui";
import usePolling from "../../hooks/usePolling";
import { useI18n } from "../../i18n/context";

export default function FarmerHome() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [devices, setDevices] = useState(null);
  const [error, setError] = useState("");

  usePolling(
    (isActive) =>
      api
        .get("/api/devices")
        .then((r) => {
          if (!isActive()) return;
          setDevices(r.data);
          setError("");
        })
        .catch(() => isActive() && setError(t("common.retrying"))),
    15000,
    []
  );

  return (
    <>
      <PageHeader eyebrow={user.name} title={t("farmer.homeTitle")} subtitle={t("farmer.homeSubtitle")} />
      <Alert>{error}</Alert>
      {!devices ? (
        <EmptyState>{t("common.loading")}</EmptyState>
      ) : devices.length === 0 ? (
        <div className="panel">
          <EmptyState>{t("farmer.noDevices")}</EmptyState>
        </div>
      ) : (
        <div className="card-grid">
          {devices.map((d) => (
            <DeviceCard key={d.device_id} device={d} to={`/farm/${d.device_id}`} />
          ))}
        </div>
      )}
    </>
  );
}
