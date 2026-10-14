import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { CheckCircle2, UserPlus } from "lucide-react";
import api, { errorMessage } from "../api";
import { homeFor, useAuth } from "../auth/context";
import { Alert } from "../components/ui";
import { useI18n } from "../i18n/context";
import AuthLayout from "../components/AuthLayout";

export default function RegisterPage() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const [form, setForm] = useState({ username: "", name: "", phone: "", village: "", password: "", confirm: "" });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homeFor(user)} replace />;

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function submit(event) {
    event.preventDefault();
    if (form.password !== form.confirm) {
      setError(t("auth.passwordsDontMatch"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.post("/api/auth/register", {
        username: form.username.trim().toLowerCase(),
        name: form.name,
        phone: form.phone,
        village: form.village,
        password: form.password,
        language: lang,
      });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err, t("common.error")));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthLayout>
        <div className="auth-done">
          <CheckCircle2 size={44} color="#239b76" />
          <p>{t("auth.registered")}</p>
          <Link className="btn btn-primary" to="/login">{t("auth.loginLink")}</Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <h2>{t("auth.registerTitle")}</h2>
      <p className="subtitle">{t("auth.registerSubtitle")}</p>
      <form className="form-stack" onSubmit={submit}>
        <label>
          {t("auth.name")}
          <input required autoComplete="name" value={form.name} onChange={set("name")} />
        </label>
        <label>
          {t("auth.username")}
          <input required autoCapitalize="none" autoComplete="username" pattern="[a-zA-Z0-9_.]{3,30}"
            value={form.username} onChange={set("username")} />
          <small>{t("auth.usernameHint")}</small>
        </label>
        <div className="form-row">
          <label>
            {t("auth.phone")}
            <input type="tel" autoComplete="tel" value={form.phone} onChange={set("phone")} />
          </label>
          <label>
            {t("auth.village")}
            <input value={form.village} onChange={set("village")} />
          </label>
        </div>
        <label>
          {t("auth.password")}
          <input type="password" required minLength={8} autoComplete="new-password" value={form.password}
            onChange={set("password")} />
          <small>{t("auth.passwordHint")}</small>
        </label>
        <label>
          {t("auth.confirmPassword")}
          <input type="password" required minLength={8} autoComplete="new-password" value={form.confirm}
            onChange={set("confirm")} />
        </label>
        <Alert>{error}</Alert>
        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          <UserPlus size={17} /> {busy ? t("common.loading") : t("auth.registerButton")}
        </button>
      </form>
      <p className="auth-switch">
        {t("auth.haveAccount")} <Link to="/login">{t("auth.loginLink")}</Link>
      </p>
    </AuthLayout>
  );
}
