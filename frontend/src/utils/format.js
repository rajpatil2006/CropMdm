/** "12 s ago" / "5 min ago" / ... in the current language. */
export function formatAgo(t, seconds) {
  if (seconds == null) return t("common.never");
  if (seconds < 120) return t("common.secondsAgo", { n: seconds });
  if (seconds < 7200) return t("common.minutesAgo", { n: Math.round(seconds / 60) });
  if (seconds < 172800) return t("common.hoursAgo", { n: Math.round(seconds / 3600) });
  return t("common.daysAgo", { n: Math.round(seconds / 86400) });
}

export function formatDateTime(iso, locale) {
  return iso ? new Date(iso).toLocaleString(locale) : "--";
}

export function formatTime(iso, locale) {
  return iso ? new Date(iso).toLocaleTimeString(locale) : "--";
}

/** Crop display name: translated for table crops, the farmer's own name for custom crops. */
export function cropName(t, has, key, fallback) {
  const k = `crop.name.${key}`;
  return has(k) ? t(k) : fallback ?? key;
}
