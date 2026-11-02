import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { t, useLanguage } from "../../i18n";
import type { I18nKey } from "../../i18n";

const examples = ["crop", "agriculture", "road", "census", "irrigation", "village", "land records"];

const scopes = ["All", "Datasets", "Tables", "Columns", "Departments"] as const;
type Scope = (typeof scopes)[number];
const scopeLabels: Record<Scope, I18nKey> = {
  All: "tabAll",
  Datasets: "tabDatasets",
  Tables: "tabTables",
  Columns: "tabColumns",
  Departments: "tabDepartments",
};

export function Hero() {
  useLanguage();
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<Scope>("All");
  const navigate = useNavigate();

  const go = (q: string, s: Scope) => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (s !== "All") params.set("scope", s.toLowerCase());
    const suffix = params.toString();
    navigate(`/explore${suffix ? `?${suffix}` : ""}`);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    go(value, scope);
  };

  return (
    <section aria-label={t("heroAria")} style={{ background: "var(--bg)" }}>
      <div className="mx-auto w-full max-w-3xl px-4 py-8 text-center sm:px-6 sm:py-10">
        <h1
          className="font-bold tracking-tight"
          style={{ color: "var(--navy-900)", fontSize: "2rem", lineHeight: 1.25 }}
        >
          {t("heroTitle")}
        </h1>
        <p
          className="mx-auto mt-3 max-w-xl"
          style={{ color: "var(--text-muted)", fontSize: "1rem" }}
        >
          {t("heroSubtitle")}
        </p>

        <form onSubmit={onSubmit} role="search" className="mt-8" aria-label={t("searchAria")}>
          <div
            className="flex w-full flex-col gap-2 sm:flex-row"
            style={{
              border: "1px solid var(--border)",
              borderRadius: 6,
              background: "var(--bg)",
              padding: 4,
            }}
          >
            <label htmlFor="registry-scope" className="sr-only">
              {t("searchScope")}
            </label>
            <select
              id="registry-scope"
              value={scope}
              onChange={(e) => setScope(e.target.value as Scope)}
              style={{
                border: "none",
                background: "var(--bg-alt)",
                borderRadius: 6,
                padding: "0.65rem 0.75rem",
                fontSize: "1rem",
                color: "var(--text)",
                minWidth: 140,
              }}
            >
              {scopes.map((s) => (
                <option key={s} value={s}>
                  {t(scopeLabels[s])}
                </option>
              ))}
            </select>
            <label htmlFor="registry-search" className="sr-only">
              {t("searchLabel")}
            </label>
            <input
              id="registry-search"
              type="search"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={t("searchPlaceholder")}
              autoComplete="off"
              className="w-full"
              style={{
                border: "none",
                flex: 1,
                padding: "0.65rem 0.75rem",
                fontSize: "1rem",
                color: "var(--text)",
                background: "transparent",
              }}
            />
            <button type="submit" className="btn-primary" style={{ whiteSpace: "nowrap" }}>
              {t("search")}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
            <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              {t("popularSearches")}
            </span>
            {examples.map((ex) => (
              <button
                key={ex}
                type="button"
                className="chip"
                onClick={() => go(ex, scope)}
                aria-label={t("searchFor", { term: ex })}
              >
                {ex}
              </button>
            ))}
          </div>
        </form>
      </div>
    </section>
  );
}
