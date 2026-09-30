import { useState } from "react";
import type { FormEvent } from "react";

const inputClass =
  "p-3 w-full border-2 rounded-lg bg-white bg-opacity-80 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 border-gray-200";

export function RequestDataset() {
  const [sent, setSent] = useState(false);

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSent(true);
  };

  return (
    <div
      className="relative mx-auto mt-10 w-11/12 rounded-xl border-2 border-white bg-slate-100 bg-opacity-60 p-6 shadow-lg md:p-8"
      style={{ backdropFilter: "blur(35px)" }}
    >
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Request a Dataset</h1>
        <p className="mt-1 text-sm text-gray-500">
          Can&apos;t find what you&apos;re looking for? Tell us and we&apos;ll work on getting it
          added.
        </p>
      </div>
      {sent ? (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          Thanks — your request has been noted. We&rsquo;ll get in touch if it aligns with our
          roadmap.
        </div>
      ) : (
        <form onSubmit={onSubmit} noValidate>
          <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <input type="text" required className={inputClass} placeholder="Full Name *" />
            </div>
            <div>
              <input type="email" required className={inputClass} placeholder="Email ID *" />
            </div>
            <div>
              <input type="text" className={inputClass} placeholder="Source Name" />
            </div>
            <div>
              <input type="url" className={inputClass} placeholder="Source URL" />
            </div>
          </div>
          <div className="flex flex-col items-start gap-4 sm:flex-row">
            <div className="flex-1">
              <textarea
                required
                className={`${inputClass} resize-none`}
                placeholder="Dataset Details * — describe what data you need, the domain, frequency, coverage, etc."
                rows={3}
              />
            </div>
            <button
              type="submit"
              className="shrink-0 rounded-lg bg-blue-500 px-6 py-3 text-sm font-semibold text-white transition-colors duration-200 hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Submit Request
            </button>
          </div>
          <p className="mt-3 text-xs text-gray-400">
            * Note: Although we are happy to receive requests for datasets from you, We also need
            to evaluate the requirements and mandates of the agency. If the request is reasonable
            and aligns with our mandates and our roadmap, we will get in touch with you to
            complete this request. So, make sure your details are correct.
          </p>
        </form>
      )}
    </div>
  );
}
