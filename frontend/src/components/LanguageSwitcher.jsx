import { Languages } from "lucide-react";
import api from "../api";
import { useAuth } from "../auth/context";
import { LANGUAGES, useI18n } from "../i18n/context";

export default function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();
  const auth = useAuth();

  function change(code) {
    setLang(code);
    // Remember the choice on the account so it follows the farmer to other phones
    if (auth?.user) {
      api.patch("/api/auth/me", { language: code }).then(() => auth.updateUser({ language: code })).catch(() => {});
    }
  }

  return (
    <label className="language-switcher" title={t("common.language")}>
      <Languages size={16} />
      <select value={lang} onChange={(e) => change(e.target.value)} aria-label={t("common.language")}>
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
