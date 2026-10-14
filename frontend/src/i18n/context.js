import { createContext, useContext } from "react";

export const I18nContext = createContext(null);

export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "mr", label: "मराठी" },
  { code: "hi", label: "हिन्दी" },
];

export function useI18n() {
  return useContext(I18nContext);
}
