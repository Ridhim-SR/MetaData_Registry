import { Hero } from "../components/registry/Hero";
import { DatasetsAtAGlance } from "../components/registry/DatasetsAtAGlance";
import { DepartmentGrid } from "../components/registry/DepartmentGrid";
import { PublicDataSection } from "../components/registry/PublicDataSection";
import { AccessCTA } from "../components/registry/AccessCTA";

export function DiscoverPage() {
  return (
    <div>
      <Hero />
      <DatasetsAtAGlance />
      <DepartmentGrid compact />
      <PublicDataSection />
      <AccessCTA />
    </div>
  );
}
