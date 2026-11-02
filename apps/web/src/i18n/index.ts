import { createElement, Fragment, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { en } from "./en";
import { hi } from "./hi";

export type Lang = "en" | "hi";
export type I18nKey = keyof typeof en;

// Both dictionaries must expose the same keys; a missing Hindi key is a
// type error here, so omissions fail the build instead of the UI.
const dicts: Record<Lang, Record<I18nKey, string>> = { en, hi };

const STORAGE_KEY = "sda-lang";

function savedLang(): Lang {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

let current: Lang = savedLang();
const listeners = new Set<() => void>();
document.documentElement.lang = current;

export function getLang(): Lang {
  return current;
}

export function setLang(next: Lang) {
  if (next === current) return;
  current = next;
  document.documentElement.lang = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Private mode / blocked storage: the switch still applies for this visit.
  }
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/**
 * Subscribes the calling component to language switches. Any component
 * that renders `t(...)` text should call this so it re-renders when the
 * header toggle changes the language; plain helpers called during that
 * render can use `t` directly.
 */
export function useLanguage() {
  const lang = useSyncExternalStore(subscribe, getLang);
  return { lang, setLang };
}

/**
 * Looks up `key` in the current language, falling back to English.
 * Supports `{name}`-style placeholders via `vars`.
 */
export function t(key: I18nKey, vars?: Record<string, string | number>): string {
  let text: string = dicts[current][key] ?? en[key];
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
  }
  return text;
}

/**
 * Like `t`, but placeholders may be React nodes (links, buttons), so a
 * sentence keeps its own word order in each language:
 * `tNodes("signInHint", { link: <Link .../> })`.
 */
export function tNodes(key: I18nKey, nodes: Record<string, ReactNode>): ReactNode[] {
  const text: string = dicts[current][key] ?? en[key];
  return text.split(/(\{\w+\})/).map((part, i) => {
    const name = /^\{(\w+)\}$/.exec(part)?.[1];
    return name && name in nodes ? createElement(Fragment, { key: i }, nodes[name]) : part;
  });
}

/** Locale for Intl number/date formatting (Indian digit grouping in both). */
export function locale(): string {
  return current === "hi" ? "hi-IN" : "en-IN";
}

export function formatNumber(n: number): string {
  return n.toLocaleString(locale());
}
