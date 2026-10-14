import { useI18n } from "../../i18n/context";
import { cropName } from "../../utils/format";

/** Translate one decision reason ({key, params}) into the current language. */
export function useReasonText() {
  const { t, has } = useI18n();
  return (reason) => {
    if (typeof reason === "string") return reason; // decisions logged by older versions
    const params = { ...reason.params };
    if (params.crop_key) params.crop = cropName(t, has, params.crop_key, params.crop);
    if (params.stage) params.stage = t(`stage.${params.stage}`);
    if (params.action) params.action = t(`action.${params.action}`);
    return t(`reason.${reason.key}`, params);
  };
}
