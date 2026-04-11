import { notFound } from "next/navigation";
import { ComponentsShowcase } from "@/components/shared/ComponentsShowcase";

export default function ComponentsPage() {
  if (process.env.NEXT_PUBLIC_APP_ENV !== "development") {
    notFound();
  }

  return <ComponentsShowcase />;
}
