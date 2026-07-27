import { ActivityStrip } from "@/components/dashboard/activity-strip";
import { PageContainer } from "@/components/shell/page-container";
import { AgentsGrid } from "@/components/dashboard/agents-grid";
import { DashboardHero } from "@/components/dashboard/hero";

export default function DashboardPage() {
  return (
    // `stagger-children`: hero, grid de agentes y actividad aterrizan en
    // cascada (~40ms), el mismo movimiento que la columna del artefacto (B3).
    <PageContainer className="stagger-children">
      <DashboardHero />
      <AgentsGrid />
      <ActivityStrip />
    </PageContainer>
  );
}
