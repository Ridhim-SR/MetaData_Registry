import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

export function HeroSearch() {
  const [value, setValue] = useState("");
  const navigate = useNavigate();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = value.trim();
    navigate(q ? `/explore?q=${encodeURIComponent(q)}` : "/explore");
  };

  return (
    <div className="relative z-10 mx-auto mb-14 w-11/12 overflow-hidden rounded-lg shadow-lg">
      <div className="relative z-10">
        <div className="relative p-4 sm:pb-4 lg:pb-4">
          <main className="px-2 sm:mt-4 sm:px-6">
            <div className="lg:grid lg:grid-cols-12 lg:gap-8">
              <div className="md:mx-2 lg:col-span-12">
                <div className="relative mt-3 text-[24px] leading-none font-light tracking-[-0.03em] uppercase md:text-[42px]">
                  Explore &amp; Visualise India&rsquo;s Public Datasets
                </div>
                <span className="mt-5 block text-sm font-semibold tracking-wide text-gray-500 uppercase sm:text-base lg:text-sm xl:text-base">
                  With FAIR principles of Findability, Accessibility, Interoperability and
                  Reusability
                </span>
                <div className="mt-8 hidden sm:block">
                  <form className="mb-5 flex" onSubmit={onSubmit}>
                    <div className="relative w-full">
                      <span className="absolute inset-y-0 left-0 flex items-center pl-6">
                        <svg
                          className="hidden h-5 w-5 text-gray-400 md:flex"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                          />
                        </svg>
                      </span>
                      <input
                        id="search2"
                        type="search"
                        name="search"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        placeholder="Search a specific dataset..."
                        aria-label="Search"
                        className="inline-block w-full rounded-full border-2 border-white bg-slate-50 py-2 pr-3 pl-4 leading-5 placeholder-gray-500 focus:border-2 focus:ring-1 focus:outline-none sm:py-4 sm:text-sm md:pl-14"
                      />
                    </div>
                  </form>
                </div>
                <div className="mt-4 sm:hidden">
                  <form className="flex gap-2" onSubmit={onSubmit}>
                    <input
                      type="search"
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                      placeholder="Search datasets..."
                      aria-label="Search"
                      className="w-full rounded-full border-2 border-white bg-slate-50 px-4 py-2 text-sm placeholder-gray-500 focus:outline-none"
                    />
                    <button
                      type="submit"
                      className="shrink-0 rounded-full bg-blue-500 px-4 py-2 text-sm font-semibold text-white"
                    >
                      Go
                    </button>
                  </form>
                </div>
              </div>
            </div>
          </main>
        </div>
      </div>
      <div
        className="absolute top-0 left-0 z-0 h-full w-full rounded-lg border-2 border-white bg-slate-100 bg-opacity-60"
        style={{ backdropFilter: "blur(35px)" }}
      />
    </div>
  );
}
