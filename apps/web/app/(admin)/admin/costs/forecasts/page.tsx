import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function CostsForecastsPage() {
  return <GenericAdminSectionPage title="Cost Forecasts" description="Forecasted spend by workspace and platform." help={<HelpContent />} />;
}
