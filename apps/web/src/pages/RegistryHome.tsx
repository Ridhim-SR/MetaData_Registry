import { AccessCTA } from "../components/registry/AccessCTA";
import { DepartmentGrid } from "../components/registry/DepartmentGrid";
import { Hero } from "../components/registry/Hero";
import { PublicDataSection } from "../components/registry/PublicDataSection";
import { StatsBar } from "../components/registry/StatsBar";

export function RegistryHomePage() {
  return (
    <div>
      <Hero />
      <StatsBar />
      <DepartmentGrid compact />
      <PublicDataSection />
      <AccessCTA />
    </div>
  );
}
