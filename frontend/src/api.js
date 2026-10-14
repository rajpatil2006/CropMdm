import axios from "axios";

// Backend address; set VITE_API_URL in frontend/.env when deployed elsewhere.
export const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

const TOKEN_KEY = "cropmind.token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage unavailable (private mode): the session lasts until the tab closes
  }
}

const api = axios.create({ baseURL: API_URL, timeout: 30000 });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// A 401 on any call means the session ended: tell the app to log out
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && getToken()) {
      window.dispatchEvent(new Event("cropmind:logout"));
    }
    return Promise.reject(error);
  }
);

/** Human-readable message from an API error. */
export function errorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg?.replace(/^Value error, /, "")).join("; ");
  if (typeof detail === "string") return detail;
  if (!error?.response) return "Cannot reach the CropMind server.";
  return fallback ?? "Something went wrong.";
}

export default api;
