import { ResetPasswordForm } from "@/components/features/auth/password-reset/ResetPasswordForm";

export default async function ResetPasswordPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  return <ResetPasswordForm token={token} />;
}
