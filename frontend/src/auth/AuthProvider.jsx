import { useCallback, useEffect, useMemo, useState } from "react";
import api, { getToken, setToken } from "../api";
import { useI18n } from "../i18n/context";
import { AuthContext } from "./context";

export default function AuthProvider({ children }) {
  const { setLang } = useI18n();
  const [user, setUser] = useState(null);
  // "checking" until a stored session has been validated with the server
  const [ready, setReady] = useState(() => !getToken());

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    if (!getToken()) return undefined;
    let active = true;
    api
      .get("/api/auth/me")
      .then((response) => {
        if (!active) return;
        setUser(response.data);
        if (response.data.language) setLang(response.data.language);
      })
      .catch(() => active && setToken(null))
      .finally(() => active && setReady(true));
    return () => {
      active = false;
    };
  }, [setLang]);

  // Any expired session anywhere in the app logs the user out
  useEffect(() => {
    window.addEventListener("cropmind:logout", logout);
    return () => window.removeEventListener("cropmind:logout", logout);
  }, [logout]);

  const login = useCallback(
    async (username, password) => {
      const response = await api.post("/api/auth/login", { username, password });
      setToken(response.data.token);
      setUser(response.data.user);
      if (response.data.user.language) setLang(response.data.user.language);
      return response.data.user;
    },
    [setLang]
  );

  const updateUser = useCallback((changes) => setUser((u) => ({ ...u, ...changes })), []);

  const value = useMemo(
    () => ({ user, ready, login, logout, updateUser }),
    [user, ready, login, logout, updateUser]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
