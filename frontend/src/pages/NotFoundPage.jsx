import { Link } from "react-router-dom";
import { homeFor, useAuth } from "../auth/context";
import { useI18n } from "../i18n/context";

export default function NotFoundPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <div className="not-found">
      <h2>404</h2>
      <p>{t("notFound.title")}</p>
      <Link className="btn btn-primary" to={user ? homeFor(user) : "/login"}>
        {t("notFound.home")}
      </Link>
    </div>
  );
}
