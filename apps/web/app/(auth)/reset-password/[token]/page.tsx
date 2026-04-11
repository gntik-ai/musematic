import { ResetPasswordForm } from "@/components/features/auth/password-reset/ResetPasswordForm";

export default function ResetPasswordPage({
  params,
}: {
  params: { token: string };
}) {
  return <ResetPasswordForm token={params.token} />;
}
