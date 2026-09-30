import { HeroSearch } from "../components/home/HeroSearch";
import { VisualiseStrip } from "../components/home/VisualiseStrip";
import { SectionDivider } from "../components/home/PublicFooter";
import { WhyIdp } from "../components/home/WhyIdp";
import { RequestDataset } from "../components/home/RequestDataset";

export function HomePage() {
  return (
    <div>
      <div className="items-center justify-center py-5 sm:mt-10">
        <HeroSearch />
        <VisualiseStrip />
        <SectionDivider />
        <SectionDivider />
        <WhyIdp />
        <SectionDivider />
        <RequestDataset />
      </div>
    </div>
  );
}
