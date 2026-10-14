import { Sprout } from "lucide-react";
import LanguageSwitcher from "./LanguageSwitcher";
import { useI18n } from "../i18n/context";

export default function AuthLayout({ children }) {
  const { t } = useI18n();
  return (
    <div className="auth-page">
      <div className="auth-top">
        <div className="brand">
          <div className="brand-icon">
            <Sprout size={22} />
          </div>
          <div>
            <h1>{t("app.name")}</h1>
            <p>{t("app.tagline")}</p>
          </div>
        </div>
        <LanguageSwitcher />
      </div>
      <div className="auth-card">{children}</div>
    </div>
  );
}
