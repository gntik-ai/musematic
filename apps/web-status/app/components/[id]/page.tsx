import { ComponentDetailClient } from "@/components/ComponentDetailClient";
import { embeddedSnapshot } from "@/lib/status-client";

type ComponentPageProps = {
  params: { id: string };
};

export function generateStaticParams() {
  return embeddedSnapshot.components.map((component) => ({ id: component.id }));
}

export default function ComponentPage({ params }: ComponentPageProps) {
  return <ComponentDetailClient componentId={params.id} />;
}
