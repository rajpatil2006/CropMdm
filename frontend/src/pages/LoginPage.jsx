import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";
import { errorMessage } from "../api";
import { homeFor, useAuth } from "../auth/context";
import AuthLayout from "../components/AuthLayout";
import { Alert } from "../components/ui";
import { useI18n } from "../i18n/context";

export default function LoginPage() {
  const { t } = useI18n();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homeFor(user)} replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const loggedIn = await login(username.trim().toLowerCase(), password);
      const from = location.state?.from;
      const allowed = from && (loggedIn.role === "admin" || !from.startsWith("/admin"));
      navigate(allowed ? from : homeFor(loggedIn), { replace: true });
    } catch (err) {
      setError(errorMessage(err, t("common.error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout>
      <h2>{t("auth.loginTitle")}</h2>
      <p className="subtitle">{t("auth.loginSubtitle")}</p>
      <form className="form-stack" onSubmit={submit}>
        <label>
          {t("auth.username")}
          <input autoComplete="username" autoCapitalize="none" required value={username}
            onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          {t("auth.password")}
          <input type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        <Alert>{error}</Alert>
        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          <LogIn size={17} /> {busy ? t("common.loading") : t("auth.loginButton")}
        </button>
      </form>
      <p className="auth-switch">
        {t("auth.noAccount")} <Link to="/register">{t("auth.createAccount")}</Link>
      </p>
    </AuthLayout>
  );
}
