import { useCallback, useMemo, useState } from "react";
import en from "./en";
import hi from "./hi";
import mr from "./mr";
import { I18nContext } from "./context";

const DICTIONARIES = { en, mr, hi };
const LANG_KEY = "cropmind.lang";

function storedLanguage() {
  try {
    return localStorage.getItem(LANG_KEY) || "en";
  } catch {
    return "en";
  }
}

export default function I18nProvider({ children }) {
  const [lang, setLangState] = useState(storedLanguage);

  const setLang = useCallback((code) => {
    if (!DICTIONARIES[code]) return;
    setLangState(code);
    try {
      localStorage.setItem(LANG_KEY, code);
    } catch {
      // ignore - language just won't be remembered
    }
  }, []);

  const value = useMemo(() => {
    const dict = DICTIONARIES[lang] ?? en;
    // t("key", {param: value}) - falls back to English, then to the key itself
    const t = (key, params) => {
      let text = dict[key] ?? en[key] ?? key;
      if (params) {
        for (const [name, v] of Object.entries(params)) {
          text = text.replaceAll(`{${name}}`, v ?? "");
        }
      }
      return text;
    };
    const has = (key) => key in dict || key in en;
    const locale = { en: "en-IN", mr: "mr-IN", hi: "hi-IN" }[lang];
    return { lang, setLang, t, has, locale };
  }, [lang, setLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
