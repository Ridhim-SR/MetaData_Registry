import { Link } from "react-router-dom";

function BarIcon() {
  return (
    <svg width="24px" height="24px" xmlns="http://www.w3.org/2000/svg">
      <rect x="6" y="14" width="2" height="6" fill="#43aaed" stroke="#43aaed" strokeWidth="2" />
      <rect x="12" y="4" width="2" height="16" fill="#01D32F" stroke="#01D32F" strokeWidth="2" />
      <rect x="18" y="10" width="2" height="10" fill="#43aaed" stroke="#43aaed" strokeWidth="2" />
    </svg>
  );
}

function LineIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="white"
      fillOpacity="0"
      stroke="#01D32F"
      className="h-6 w-6"
    >
      <path
        fillRule="evenodd"
        d="M2.25 2.25a.75.75 0 000 1.5H3v10.5a3 3 0 003 3h1.21l-1.172 3.513a.75.75 0 001.424.474l.329-.987h8.418l.33.987a.75.75 0 001.422-.474l-1.17-3.513H18a3 3 0 003-3V3.75h.75a.75.75 0 000-1.5H2.25zm6.54 15h6.42l.5 1.5H8.29l.5-1.5zm8.085-8.995a.75.75 0 10-.75-1.299 12.81 12.81 0 00-3.558 3.05L11.03 8.47a.75.75 0 00-1.06 0l-3 3a.75.75 0 101.06 1.06l2.47-2.47 1.617 1.618a.75.75 0 001.146-.102 11.312 11.312 0 013.612-3.321z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function PieIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#01D32F" className="h-6 w-6">
      <path
        fillRule="evenodd"
        d="M2.25 13.5a8.25 8.25 0 018.25-8.25.75.75 0 01.75.75v6.75H18a.75.75 0 01.75.75 8.25 8.25 0 01-16.5 0z"
        fill="#43aaed"
        clipRule="evenodd"
      />
      <path
        fillRule="evenodd"
        d="M12.75 3a.75.75 0 01.75-.75 8.25 8.25 0 018.25 8.25.75.75 0 01-.75.75h-7.5a.75.75 0 01-.75-.75V3z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function TableIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="white"
      fillOpacity="0"
      stroke="#01D32F"
      className="h-6 w-6"
    >
      <path
        fillRule="evenodd"
        d="M1.5 5.625c0-1.036.84-1.875 1.875-1.875h17.25c1.035 0 1.875.84 1.875 1.875v12.75c0 1.035-.84 1.875-1.875 1.875H3.375A1.875 1.875 0 011.5 18.375V5.625zM21 9.375A.375.375 0 0020.625 9h-7.5a.375.375 0 00-.375.375v1.5c0 .207.168.375.375.375h7.5a.375.375 0 00.375-.375v-1.5zm0 3.75a.375.375 0 00-.375-.375h-7.5a.375.375 0 00-.375.375v1.5c0 .207.168.375.375.375h7.5a.375.375 0 00.375-.375v-1.5zm0 3.75a.375.375 0 00-.375-.375h-7.5a.375.375 0 00-.375.375v1.5c0 .207.168.375.375.375h7.5a.375.375 0 00.375-.375v-1.5zM10.875 18.75a.375.375 0 00.375-.375v-1.5a.375.375 0 00-.375-.375h-7.5a.375.375 0 00-.375.375v1.5c0 .207.168.375.375.375h7.5zM3.375 15h7.5a.375.375 0 00.375-.375v-1.5a.375.375 0 00-.375-.375h-7.5a.375.375 0 00-.375.375v1.5c0 .207.168.375.375.375zm0-3.75h7.5a.375.375 0 00.375-.375v-1.5A.375.375 0 0010.875 9h-7.5A.375.375 0 003 9.375v1.5c0 .207.168.375.375.375z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ScatterIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="#43aaed" strokeWidth={2}>
      <circle cx="6" cy="18" r="1.6" fill="#43aaed" />
      <circle cx="10" cy="14" r="1.6" fill="#01D32F" stroke="#01D32F" />
      <circle cx="14" cy="10" r="1.6" fill="#43aaed" />
      <circle cx="18" cy="6" r="1.6" fill="#01D32F" stroke="#01D32F" />
    </svg>
  );
}

function MapIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="#43aaed">
      <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zm0 2.3 6 2v9.4l-6-2V6.3z" />
    </svg>
  );
}

const items = [
  { label: "Bar", Icon: BarIcon },
  { label: "Line", Icon: LineIcon },
  { label: "Pie", Icon: PieIcon },
  { label: "Table", Icon: TableIcon },
  { label: "Scatter", Icon: ScatterIcon },
  { label: "Map", Icon: MapIcon },
];

export function VisualiseStrip() {
  return (
    <div
      className="relative z-0 mx-auto mt-10 grid w-11/12 grid-cols-1 rounded-xl border-2 border-white p-4 shadow-lg sm:p-10 lg:grid-cols-1"
      style={{
        backgroundImage:
          "linear-gradient(113deg, rgba(255, 255, 255, 0.33) 3.51%, rgba(255, 255, 255, 0.38) 111.71%)",
      }}
    >
      <div className="flex flex-col justify-between md:flex-row lg:flex-row">
        <div className="p-0 xl:p-5" style={{ zIndex: 10, display: "flex", alignItems: "center" }}>
          <p className="font-inter text-[20px] font-normal lg:text-[32px]">Visualise</p>
        </div>
        <div className="inline-grid md:flex">
          {items.map(({ label, Icon }) => (
            <Link
              key={label}
              to={`/explore?visual=${label.toLowerCase()}`}
              className="m-1 flex cursor-pointer items-center justify-center rounded-3xl border-2 border-solid border-blue-500 px-2.5 py-2.5 text-blue-500 hover:bg-blue-100 sm:px-5 md:p-2 lg:m-3 lg:p-2.5 xl:m-6 xl:px-4 xl:py-2.5"
            >
              <span>
                <Icon />
              </span>
              <span className="ml-2">{label}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
