import { OAuthCallbackHandler } from "@/components/features/auth/OAuthCallbackHandler";

interface OAuthCallbackPageProps {
  params: Promise<{ provider: string }>;
}

export default async function OAuthCallbackPage({ params }: OAuthCallbackPageProps) {
  const { provider } = await params;
  return <OAuthCallbackHandler provider={provider} />;
}
