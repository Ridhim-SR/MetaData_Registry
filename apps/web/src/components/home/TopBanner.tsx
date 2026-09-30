import { useState } from "react";

export function TopBanner() {
  const [visible, setVisible] = useState(true);
  if (!visible) return null;

  return (
    <div className="relative w-full bg-[#DFF7FF] p-2 text-center text-sm font-medium text-blue-500">
      <span className="mr-1">Looking for the documentation?</span>
      <a
        href="https://devdocs.indiadataportal.com"
        target="_blank"
        rel="noopener noreferrer"
        className="cursor-pointer font-bold text-blue-700 underline transition duration-200 hover:text-blue-600"
      >
        Click here →
      </a>
      <button
        onClick={() => setVisible(false)}
        aria-label="Close"
        className="absolute top-1/2 right-4 -translate-y-1/2 text-lg font-bold text-blue-500 transition duration-200 hover:text-red-500"
      >
        ×
      </button>
    </div>
  );
}
