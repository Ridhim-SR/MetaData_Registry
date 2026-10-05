import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

const examples = ["crop", "agriculture", "road", "census", "irrigation", "village", "land records"];

export function Hero() {
  const [value, setValue] = useState("");
  const navigate = useNavigate();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = value.trim();
    navigate(q ? `/explore?q=${encodeURIComponent(q)}` : "/explore");
  };

  return (
    <section className="border-b border-slate-200 bg-white">
      {/* Narrow container: caps line length for readability on wide displays */}
      <div className="mx-auto w-full max-w-3xl px-4 py-12 text-center sm:px-6 sm:py-16">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Discover Government Data &amp; Metadata
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-base text-slate-600">
          Find datasets, understand their structure, ownership, availability and access level.
        </p>
        <form onSubmit={onSubmit} role="search" className="mt-8">
          <label htmlFor="registry-search" className="sr-only">
            Search datasets, tables, keywords
          </label>
          <div className="relative">
            <span aria-hidden className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4 text-slate-400">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </span>
            <input
              id="registry-search"
              type="search"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Search datasets, tables, keywords..."
              autoComplete="off"
              className="w-full rounded-full border border-slate-300 bg-white py-3 pr-4 pl-11 text-base shadow-sm placeholder:text-slate-400 focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none"
            />
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Try:{" "}
            {examples.map((ex, i) => (
              <span key={ex}>
                <button
                  type="button"
                  onClick={() => navigate(`/explore?q=${encodeURIComponent(ex)}`)}
                  className="underline hover:text-slate-800"
                >
                  {ex}
                </button>
                {i < examples.length - 1 && " · "}
              </span>
            ))}
          </p>
        </form>
        <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
          <button
            onClick={() => navigate("/explore?visibility=public")}
            className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-slate-700"
          >
            Browse Public Data
          </button>
          <button
            onClick={() => navigate("/explore")}
            className="rounded-full border border-slate-300 bg-white px-6 py-2.5 text-sm font-medium text-slate-900 hover:bg-slate-100"
          >
            Browse Catalog
          </button>
        </div>
      </div>
    </section>
  );
}
