import { Link, Outlet } from "react-router-dom";
import { RegistryHeader } from "./registry/RegistryHeader";

export function RegistryLayout() {
  const year = new Date().getFullYear();
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900">
      <RegistryHeader />
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-slate-200 bg-gradient-to-r from-white via-slate-50 to-amber-50">
        <div className="mx-auto grid w-full max-w-7xl grid-cols-2 items-center gap-6 px-4 py-6 text-sm text-slate-900 sm:px-6 md:grid-cols-4 lg:px-8">
          <p className="text-xs text-slate-600 sm:text-sm">
            © {year} SDA Metadata Registry. All rights reserved
          </p>
          <div className="flex items-center gap-6">
            <img
              src="/isb-logo.webp"
              alt="ISB Bharti Institute of Public Policy"
              className="h-10 w-auto"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
            {/* <GatesWordmark /> */}
          </div>
          <Link to="/privacy" className="hover:underline md:text-center">
            Data Privacy Policy
          </Link>
          <Link to="/copyrights" className="hover:underline md:text-center">
            Copyrights Policy
          </Link>
        </div>
      </footer>
    </div>
  );
}
