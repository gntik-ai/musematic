export default function AuthLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-12">
      <div className="surface-grid absolute inset-0 opacity-40" />
      <div className="relative z-10 w-full max-w-lg">{children}</div>
    </div>
  );
}
