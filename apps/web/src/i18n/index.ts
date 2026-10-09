import { en } from "./en";
import { hi } from "./hi";

export type I18nKey = keyof typeof en;

// Both dictionaries must expose the same keys; a missing Hindi key is a
// type error here, so omissions fail the build instead of the UI.
const dicts: Record<"en" | "hi", Record<I18nKey, string>> = { en, hi };

function currentLang(): "en" | "hi" {
  try {
    // Same storage key the header language switcher writes.
    return window.localStorage.getItem("sda-lang") === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

/**
 * Minimal lookup for the Table page additions (the app has no i18n
 * provider yet; this reads the saved language on every render).
 * Supports `{name}`-style placeholders via `vars`.
 */
export function t(key: I18nKey, vars?: Record<string, string>): string {
  const lang = currentLang();
  let text: string = dicts[lang][key] ?? en[key];
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replace(`{${name}}`, value);
    }
  }
  return text;
}
