import { Hero } from "../components/registry/Hero";
import { StatsBar } from "../components/registry/StatsBar";
import { DepartmentGrid } from "../components/registry/DepartmentGrid";
import { PublicDataSection } from "../components/registry/PublicDataSection";
import { HowItWorks } from "../components/registry/HowItWorks";
import { AccessCTA } from "../components/registry/AccessCTA";

export function RegistryHomePage() {
  return (
    <div>
      <Hero />
      <StatsBar />
      <DepartmentGrid compact />
      <PublicDataSection />
      <HowItWorks />
      <AccessCTA />
    </div>
  );
}
