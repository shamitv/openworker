// Vitest global setup: initialize i18n synchronously so t() resolves inside
// components under test. Uses the English resources so existing English
// assertions keep working; without this, t("key") renders the key literal.
import type {} from "vitest/jsdom";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";

// Node can expose its own localStorage before Vitest initializes jsdom.
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  writable: true,
  value: jsdom.window.localStorage,
});

i18n.use(initReactI18next).init({
  resources: { en: { translation: en } },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});
