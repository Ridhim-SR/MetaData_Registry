import { Link } from "react-router-dom";

function Divider() {
  return (
    <div className="relative mx-auto mt-5 flex w-11/12 items-center py-5">
      <div className="flex-grow border-t border-gray-400" />
      <div className="flex-grow border-t border-gray-400" />
    </div>
  );
}

export function SectionDivider() {
  return <Divider />;
}

export function PublicFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="mx-auto w-full md:w-11/12">
      <div className="relative mx-auto mt-5 flex w-full items-center py-3 md:py-5">
        <div className="flex-grow border-t border-gray-400" />
        <div className="flex-grow border-t border-gray-400" />
      </div>
      <div className="grid grid-cols-1 gap-4 p-4 pb-4 md:grid-cols-2 md:gap-6 md:p-5 md:pb-10 lg:grid-cols-3 lg:gap-20">
        <div className="mt-12 text-center md:text-left">
          <p className="text-xs md:text-sm">© {year} India Data Portal. All rights reserved</p>
        </div>
        <div className="text-center md:text-left">
          <div className="mt-1 grid grid-cols-2 gap-4">
            <div className="mt-7 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700">
              ISB · BIPP
            </div>
            <div className="mt-8 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700">
              BMGF
            </div>
          </div>
        </div>
        <div className="text-center md:text-right">
          <div className="mt-12 grid grid-cols-2 gap-4">
            <div>
              <Link to="/datausage?view=data_privacy_policy" className="relative bottom-7 md:bottom-0">
                Data Privacy Policy
              </Link>
            </div>
            <div>
              <Link to="/datausage?view=copyright_policy" className="relative bottom-7 md:bottom-0">
                Copyrights Policy
              </Link>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
