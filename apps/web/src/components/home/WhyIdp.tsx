function WhyIllustration() {
  return (
    <svg viewBox="0 0 400 200" className="mx-auto h-auto w-full max-w-[360px]" role="img" aria-label="Why IDP illustration">
      <rect x="20" y="20" width="360" height="160" rx="16" fill="#E6F4FF" />
      <rect x="45" y="50" width="120" height="14" rx="7" fill="#316FDE" opacity="0.85" />
      <rect x="45" y="72" width="200" height="10" rx="5" fill="#9EC1FF" />
      <rect x="45" y="90" width="170" height="10" rx="5" fill="#BFE3FF" />
      <circle cx="310" cy="90" r="34" fill="#00B962" opacity="0.85" />
      <rect x="292" y="78" width="36" height="10" rx="5" fill="white" />
      <rect x="292" y="94" width="24" height="10" rx="5" fill="white" opacity="0.8" />
      <rect x="45" y="115" width="90" height="32" rx="16" fill="#316FDE" />
      <rect x="145" y="115" width="90" height="32" rx="16" fill="white" stroke="#316FDE" strokeWidth="2" />
    </svg>
  );
}

const points = [
  "No paywall for public datasets",
  "Data in public domain and from the government sources will be free to use and interpret",
  "IDP provides interoperability among datasets. Users can merge datasets using the using local directory codes for better insights and analysis",
  "Users can upload their own datasets to visualise on the portal",
  "Users can download complete data",
];

export function WhyIdp() {
  return (
    <div
      id="why-idp"
      className="relative mx-auto mt-10 w-11/12 rounded-xl border-2 border-white p-0 pb-2 shadow-lg"
      style={{ backdropFilter: "blur(35px)" }}
    >
      <div className="relative z-0 grid grid-cols-5">
        <div className="col-span-5 mt-10 mb-10 lg:mt-20 xl:col-span-2">
          <WhyIllustration />
        </div>
        <div className="col-span-5 mt-2 mb-6 lg:mt-6 xl:col-span-3">
          <h1 className="mt-2 ml-10 text-[24px] font-medium sm:text-[32px] lg:mt-7 lg:ml-0">
            Why IDP?
          </h1>
          <div className="mt-2 ml-10 pr-10 lg:mt-10 lg:ml-0">
            <div className="text-xl font-normal sm:text-base">
              <p className="mb-5">
                With India Data portal, users get an uninhibited access to free and reliable,
                value-added data/datasets. Here are some advantages of utilising IDP:
              </p>
              <ul className="ml-5 list-disc">
                {points.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
      <div
        className="absolute top-0 left-0 z-0 h-full w-full rounded-lg bg-slate-100 opacity-60"
        style={{ backdropFilter: "blur(35px)" }}
      />
    </div>
  );
}
