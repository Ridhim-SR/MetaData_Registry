import {
  HomeAbout,
  HomeHero,
} from "../components/registry/HomeSections";
import { HowItWorks } from "../components/registry/HowItWorks";

// Landing page. Search, stats and dataset listings live on the Discover page.
export function RegistryHomePage() {
  return (
    <div>
      <HomeHero />
      <HomeAbout />
      <HowItWorks />
    </div>
  );
}
