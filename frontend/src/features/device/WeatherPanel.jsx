import { CloudSun } from "lucide-react";
import { EmptyState, Panel, Row } from "../../components/ui";
import { useI18n } from "../../i18n/context";

export default function WeatherPanel({ weather }) {
  const { t, locale } = useI18n();

  if (!weather) {
    return (
      <Panel title={t("weather.title")}>
        <EmptyState>{t("common.loading")}</EmptyState>
      </Panel>
    );
  }

  return (
    <Panel
      title={t("weather.title")}
      subtitle={
        <>
          {t("weather.subtitle")}{" "}
          <span className={`pill pill-${weather.reliability}`}>{t(`weather.${weather.reliability}`)}</span>
        </>
      }
      icon={<CloudSun size={21} color="#3686e8" />}
    >
      <Row label={t("weather.rain24")} value={`${weather.rain_next_24h_mm} mm`} />
      <Row label={t("weather.rain48")} value={`${weather.rain_next_48h_mm} mm`} />
      <Row label={t("weather.maxProb")} value={`${weather.rain_probability_24h}%`} />
      <Row
        label={t("weather.rainStarts")}
        value={weather.hours_until_rain == null ? t("weather.noneForecast") : `${weather.hours_until_rain} h`}
      />
      <Row label={t("weather.et0")} value={`${weather.et0_used_mm} mm/day`} />

      {weather.days?.length > 0 && (
        <div className="forecast-days">
          {weather.days.map((d) => (
            <div key={d.date} className="forecast-day">
              <span>{new Date(d.date).toLocaleDateString(locale, { weekday: "short" })}</span>
              <strong>
                {d.tmax}° / {d.tmin}°
              </strong>
              <small>
                {d.rain_mm} mm · {d.rain_probability}%
              </small>
            </div>
          ))}
        </div>
      )}
      <p className="note">{t("weather.et0Source", { source: weather.et0_source })}</p>
    </Panel>
  );
}
