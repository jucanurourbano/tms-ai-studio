import { ActivityStrip } from "@/components/dashboard/activity-strip";
import { AgentsGrid } from "@/components/dashboard/agents-grid";
import { DashboardHero } from "@/components/dashboard/hero";

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-6xl p-6">
      <DashboardHero />
      <AgentsGrid />
      <ActivityStrip />
    </div>
  );
}
