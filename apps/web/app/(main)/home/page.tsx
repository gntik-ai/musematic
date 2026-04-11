import type { Metadata } from "next";
import { HomeDashboard } from "@/components/features/home/HomeDashboard";

export const metadata: Metadata = {
  title: "Home | Musematic Agentic Mesh",
  description: "Workspace home dashboard with live metrics, activity, and pending actions.",
};

export default function HomePage() {
  return <HomeDashboard />;
}
