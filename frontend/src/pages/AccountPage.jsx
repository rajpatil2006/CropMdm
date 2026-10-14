import { useState } from "react";
import api, { errorMessage } from "../api";
import { useAuth } from "../auth/context";
import { Alert, PageHeader, Panel, Row } from "../components/ui";
import { useI18n } from "../i18n/context";

export default function AccountPage() {
  const { t } = useI18n();
  const { user, updateUser } = useAuth();
  const [profile, setProfile] = useState({ name: user.name ?? "", phone: user.phone ?? "", village: user.village ?? "" });
  const [profileMsg, setProfileMsg] = useState(null);
  const [passwords, setPasswords] = useState({ current: "", next: "", confirm: "" });
  const [passwordMsg, setPasswordMsg] = useState(null);

  async function saveProfile(event) {
    event.preventDefault();
    try {
      const r = await api.patch("/api/auth/me", profile);
      updateUser(r.data);
      setProfileMsg({ tone: "success", text: t("account.profileSaved") });
    } catch (err) {
      setProfileMsg({ tone: "error", text: errorMessage(err, t("common.error")) });
    }
  }

  async function changePassword(event) {
    event.preventDefault();
    if (passwords.next !== passwords.confirm) {
      setPasswordMsg({ tone: "error", text: t("auth.passwordsDontMatch") });
      return;
    }
    try {
      await api.post("/api/auth/change-password", {
        current_password: passwords.current,
        new_password: passwords.next,
      });
      setPasswords({ current: "", next: "", confirm: "" });
      setPasswordMsg({ tone: "success", text: t("account.passwordChanged") });
    } catch (err) {
      setPasswordMsg({ tone: "error", text: errorMessage(err, t("common.error")) });
    }
  }

  return (
    <>
      <PageHeader title={t("account.title")} subtitle={`@${user.username}`} />
      <div className="grid-2">
        <Panel title={t("account.profile")}>
          <Row label={t("auth.username")} value={user.username} />
          <Row label={t("account.role")} value={user.role === "admin" ? "Administrator" : t("pump.byFarmer")} />
          <form className="form-stack" onSubmit={saveProfile}>
            <label>
              {t("auth.name")}
              <input required value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
            </label>
            <label>
              {t("auth.phone")}
              <input type="tel" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} />
            </label>
            <label>
              {t("auth.village")}
              <input value={profile.village} onChange={(e) => setProfile({ ...profile, village: e.target.value })} />
            </label>
            {profileMsg && <Alert tone={profileMsg.tone}>{profileMsg.text}</Alert>}
            <button className="btn btn-primary" type="submit">{t("account.saveProfile")}</button>
          </form>
        </Panel>

        <Panel title={t("account.changePassword")}>
          <form className="form-stack" onSubmit={changePassword}>
            <label>
              {t("account.currentPassword")}
              <input type="password" required autoComplete="current-password" value={passwords.current}
                onChange={(e) => setPasswords({ ...passwords, current: e.target.value })} />
            </label>
            <label>
              {t("account.newPassword")}
              <input type="password" required minLength={8} autoComplete="new-password" value={passwords.next}
                onChange={(e) => setPasswords({ ...passwords, next: e.target.value })} />
              <small>{t("auth.passwordHint")}</small>
            </label>
            <label>
              {t("auth.confirmPassword")}
              <input type="password" required minLength={8} autoComplete="new-password" value={passwords.confirm}
                onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} />
            </label>
            {passwordMsg && <Alert tone={passwordMsg.tone}>{passwordMsg.text}</Alert>}
            <button className="btn btn-primary" type="submit">{t("account.changePassword")}</button>
          </form>
        </Panel>
      </div>
    </>
  );
}
