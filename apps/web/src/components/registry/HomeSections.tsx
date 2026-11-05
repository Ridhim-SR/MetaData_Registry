import { Link } from "react-router-dom";
import { t, useLanguage } from "../../i18n";
import type { I18nKey } from "../../i18n";
import { Icon, IconTile } from "./Icons";
import type { IconName } from "./Icons";

// Sections of the landing page (Home). Search and the full listings live on Discover.

const container = "page-container mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8";

// ── Hero ────────────────────────────────────────────────────────────────

// Illustrative only: the kinds of sources departments describe, not live data.
const IN_LINES: Array<{ y: number; color: string; label: I18nKey }> = [
  { y: 30, color: "var(--blue-700)", label: "homeFlowSystems" },
  { y: 90, color: "var(--saffron)", label: "homeFlowDatabases" },
  { y: 150, color: "var(--public-fg)", label: "homeFlowSpreadsheets" },
  { y: 210, color: "var(--navy-900)", label: "homeFlowRecords" },
];
// Out of the registry, the lines spread and meet again at a single "Users" badge.
const OUT_LINES = [
  { y: 50, color: "var(--blue-700)" },
  { y: 120, color: "var(--saffron)" },
  { y: 190, color: "var(--public-fg)" },
];

// What the registry records for each dataset (shown inside the hero's registry card).
const CATALOGUED: I18nKey[] = ["homeCardDefinitions", "homeCardOwners", "homeCardAccess", "homeCardTiers"];

export function HomeHero() {
  useLanguage();

  return (
    <section aria-labelledby="home-hero-title" style={{ background: "var(--bg)" }}>
      <div className={`${container} pt-12 pb-6 text-center`}>
        <p className="font-semibold" style={{ color: "var(--saffron-text)", fontSize: "0.875rem" }}>
          {t("govUP")}
        </p>
        <h1
          id="home-hero-title"
          className="mx-auto mt-2 max-w-3xl font-bold tracking-tight"
          style={{ color: "var(--navy-900)", fontSize: "clamp(1.75rem, 4vw, 2.5rem)", lineHeight: 1.2 }}
        >
          {t("homeHeroTitle")}
        </h1>
        <p className="mx-auto mt-3 max-w-2xl" style={{ color: "var(--text-muted)", fontSize: "1.0625rem" }}>
          {t("homeHeroSubtitle")}
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link to="/discover" className="btn-primary">
            {t("homeExploreCta")} <span aria-hidden="true" style={{ marginLeft: 6 }}>→</span>
          </Link>
          <a href="#how-it-works" className="btn-secondary">
            {t("howTitle")}
          </a>
        </div>
      </div>

      {/* Decorative: department metadata converging on the registry, then reaching users. */}
      <div className={`${container} hidden pb-10 sm:block`}>
        <svg viewBox="0 0 1000 240" width="100%" role="img" aria-label={t("homeFlowAria")}>
          <g fill="none" strokeWidth={2} strokeLinecap="round">
            {IN_LINES.map((l) => (
              <path
                key={l.y}
                className="flow-line"
                d={`M0 ${l.y} C220 ${l.y} 230 120 385 120`}
                style={{ stroke: l.color }}
              />
            ))}
            {OUT_LINES.map((l) => (
              <path
                key={l.y}
                className="flow-line"
                d={`M615 120 C690 120 700 ${l.y} 780 ${l.y} C860 ${l.y} 870 120 938 120`}
                style={{ stroke: l.color }}
              />
            ))}
          </g>

          {IN_LINES.map((l) => (
            // Lines below the card's centre curve upwards, so their label sits under the line.
            <text
              key={l.label}
              x={2}
              y={l.y > 120 ? l.y + 20 : l.y - 9}
              style={{ fill: "var(--text-muted)", fontSize: 13 }}
            >
              {t(l.label)}
            </text>
          ))}
          {/* End users: one badge, since the registry is open to anyone who needs the metadata. */}
          <circle cx={966} cy={120} r={28} style={{ fill: "var(--navy-900)" }} />
          <g transform="translate(952 106)" style={{ color: "#fff" }}>
            <Icon name="users" size={28} />
          </g>
          <text x={966} y={170} textAnchor="middle" style={{ fill: "var(--navy-900)", fontSize: 14, fontWeight: 700 }}>
            {t("homeFlowUsers")}
          </text>

          {/* The registry card: what gets catalogued for every dataset. */}
          <rect x={385} y={35} width={230} height={170} rx={10} style={{ fill: "var(--bg)", stroke: "var(--border)" }} />
          <rect x={385} y={35} width={230} height={30} rx={10} style={{ fill: "var(--navy-900)" }} />
          <rect x={385} y={53} width={230} height={12} style={{ fill: "var(--navy-900)" }} />
          <text x={500} y={55} textAnchor="middle" style={{ fill: "#fff", fontSize: 13, fontWeight: 600 }}>
            {t("footerSiteName")}
          </text>
          <foreignObject x={397} y={73} width={210} height={126}>
            <ul className="home-card-list">
              {CATALOGUED.map((k) => (
                <li key={k}>
                  <span aria-hidden="true">✓</span>
                  {t(k)}
                </li>
              ))}
            </ul>
          </foreignObject>
        </svg>
      </div>
    </section>
  );
}

// ── About ───────────────────────────────────────────────────────────────

const PRINCIPLES: Array<{ icon: IconName; title: I18nKey; body: I18nKey }> = [
  { icon: "landmark", title: "homeCustodyTitle", body: "homeCustodyBody" },
  { icon: "layers", title: "homeStandardTitle", body: "homeStandardBody" },
  { icon: "shieldCheck", title: "homeClassifiedTitle", body: "homeClassifiedBody" },
];

export function HomeAbout() {
  useLanguage();
  return (
    <section aria-labelledby="home-about-title" style={{ background: "var(--bg)", borderTop: "1px solid var(--border)" }}>
      <div className={`${container} grid grid-cols-1 gap-8 py-12 lg:grid-cols-12`}>
        <div className="lg:col-span-7">
          <h2
            id="home-about-title"
            className="font-bold"
            style={{ color: "var(--navy-900)", fontSize: "1.75rem", lineHeight: 1.25 }}
          >
            {t("footerAbout")}
          </h2>
          <p className="mt-4" style={{ color: "var(--text)", lineHeight: 1.7 }}>
            {t("aboutRegistryP1")}
          </p>
          <p className="mt-4" style={{ color: "var(--text)", lineHeight: 1.7 }}>
            {t("aboutRegistryP2")}
          </p>
        </div>
        <ul className="grid list-none content-start gap-4 p-0 lg:col-span-5">
          {PRINCIPLES.map((p) => (
            <li
              key={p.title}
              className="flex items-start gap-4 p-5"
              style={{ border: "1px solid var(--border)", borderRadius: 10, background: "var(--bg-alt)" }}
            >
              <IconTile name={p.icon} />
              <div>
                <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
                  {t(p.title)}
                </h3>
                <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                  {t(p.body)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
