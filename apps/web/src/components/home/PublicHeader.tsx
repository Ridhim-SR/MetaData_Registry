import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { displayName } from "../../api/auth";
import { useAuth } from "../../contexts/AuthContext";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `relative block cursor-pointer p-5 text-sm font-medium xl:text-base hover:bg-gray-50 md:hover:bg-transparent ${
    isActive ? "text-blue-600" : "text-black"
  }`;

function Logo() {
  return (
    <Link to="/" className="flex items-center">
      <div className="flex h-12 items-center gap-2 lg:h-14">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-700 font-bold text-white">
          IDP
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold text-slate-900">India Data Portal</div>
          <div className="text-[11px] font-medium text-slate-500">ISB · Bharti Institute</div>
        </div>
      </div>
    </Link>
  );
}

export function PublicHeader() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleAuthClick = () => {
    if (isAuthenticated) {
      logout();
      navigate("/");
    } else {
      navigate("/login");
    }
  };

  return (
    <div
      className="relative z-10 mx-auto w-full bg-white"
      style={{ boxShadow: "0px 4px 15px rgba(0, 0, 0, 0.05)" }}
    >
      <div className="ml-0 p-3 sm:ml-5 md:p-0 lg:ml-6">
        <nav className="border-gray-200">
          <div className="container mx-auto mt-2 flex flex-wrap items-center justify-start md:mt-0">
            <div className="hidden md:flex lg:ml-7">
              <Logo />
            </div>

            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="z-50 inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-900 focus:ring-2 focus:ring-blue-300 focus:outline-none md:hidden"
              aria-controls="mobile-menu"
              aria-expanded={open}
            >
              <span className="sr-only">Open main menu</span>
              <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
            <div className="z-30 ml-2 flex md:hidden">
              <Logo />
            </div>

            <div className="z-30 ml-auto flex items-center text-xs sm:hidden">
              <button
                onClick={handleAuthClick}
                className="rounded-full border-2 border-blue-400 bg-white px-2 py-1 text-xs font-medium text-blue-500"
              >
                {isAuthenticated ? "Sign out" : "Sign in"}
              </button>
            </div>

            <div
              id="mobile-menu"
              className={`${open ? "block" : "hidden"} w-full md:block md:w-auto`}
              style={{ zIndex: 10 }}
            >
              <ul className="mt-4 ml-2 flex flex-col pl-0 md:mt-0 md:ml-16 md:flex-row md:text-sm md:font-medium lg:ml-16">
                <li className="relative h-full">
                  <NavLink to="/" end className={navLinkClass}>
                    Home
                  </NavLink>
                </li>
                <li className="relative h-full">
                  <NavLink to="/explore" className={navLinkClass}>
                    Datasets
                  </NavLink>
                </li>
                <li className="relative h-full">
                  <a href="#why-idp" className={navLinkClass({ isActive: false })}>
                    About
                  </a>
                </li>
                <li className="relative h-full">
                  <NavLink to="/explore" className={navLinkClass}>
                    IDP Spot
                    <span className="absolute -top-1 -right-1 animate-pulse rounded-full bg-gradient-to-r from-blue-500 to-blue-600 px-2 py-0.5 text-[10px] font-bold text-white shadow-md">
                      NEW
                    </span>
                  </NavLink>
                </li>
                {isAuthenticated && (
                  <li className="relative h-full">
                    <NavLink to="/dashboard" className={navLinkClass}>
                      Dashboard
                    </NavLink>
                  </li>
                )}
              </ul>
            </div>

            <div className="ml-auto hidden items-center gap-3 sm:flex md:mr-7 lg:mr-11">
              <div className="group hidden cursor-pointer items-center sm:flex">
                <span className="text-xl" role="img" aria-label="feedback">
                  💬
                </span>
                <div className="ml-2 hidden font-medium whitespace-nowrap group-hover:block">
                  Share Feedback
                </div>
              </div>
              <div className="p-2 md:pt-5">
                {isAuthenticated ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-600 sm:text-sm">
                      {displayName(user) || user?.email}
                    </span>
                    <button
                      onClick={handleAuthClick}
                      className="rounded-full border-2 border-blue-400 bg-white px-2 py-1 text-xs font-medium text-blue-500 hover:text-blue-600 sm:px-4 sm:text-base"
                    >
                      Sign out
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={handleAuthClick}
                    className="rounded-full border-2 border-blue-400 bg-white px-2 py-1 text-xs font-medium text-blue-500 hover:text-blue-600 sm:px-4 sm:text-base"
                  >
                    Sign in
                  </button>
                )}
              </div>
            </div>
          </div>
        </nav>
      </div>
    </div>
  );
}
