import { Outlet } from "react-router-dom";
import { BackgroundBlobs } from "./home/BackgroundBlobs";
import { TopBanner } from "./home/TopBanner";
import { PublicHeader } from "./home/PublicHeader";
import { PublicFooter } from "./home/PublicFooter";

export function PublicLayout() {
  return (
    <main
      className="relative h-full w-full overflow-x-hidden overflow-y-hidden"
      style={{
        fontFamily: "Inter, sans-serif",
        backgroundImage:
          "linear-gradient(138.96deg, #DFF7FF 21.9%, rgba(209, 234, 254, 0) 82.95%)",
        backgroundRepeat: "no-repeat",
        backgroundSize: "auto 100%",
        backgroundPosition: "center",
      }}
    >
      <BackgroundBlobs />
      <TopBanner />
      <PublicHeader />
      <Outlet />
      <div className="flex min-h-[20vh] flex-col">
        <div className="flex-grow" />
        <PublicFooter />
      </div>
    </main>
  );
}
