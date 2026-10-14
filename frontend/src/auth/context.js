import { createContext, useContext } from "react";

export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

/** Where each role lands after logging in. */
export function homeFor(user) {
  return user?.role === "admin" ? "/admin" : "/farm";
}
