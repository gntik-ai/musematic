export default function AuthLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-12">
      <div className="surface-grid absolute inset-0 opacity-30" />
      <div className="absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-brand-primary/15 to-transparent blur-3xl" />
      <div className="relative z-10 grid w-full max-w-6xl gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <div className="hidden space-y-6 lg:block">
          <div className="inline-flex items-center gap-3 rounded-full border border-brand-primary/20 bg-card/80 px-4 py-2 backdrop-blur">
            <div className="h-2.5 w-2.5 rounded-full bg-brand-accent" />
            <span className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-primary">
              Musematic Control Surface
            </span>
          </div>
          <div className="max-w-xl space-y-4">
            <h1 className="text-5xl font-semibold tracking-tight text-foreground">
              Trust the workflow, not the tab chaos.
            </h1>
            <p className="text-lg text-muted-foreground">
              Secure access for operators, auditors, and workspace admins with
              MFA, recovery codes, and reset flows built into the shell.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-border/70 bg-card/80 p-5 backdrop-blur">
              <p className="text-sm font-semibold text-foreground">Password reset without enumeration</p>
              <p className="mt-2 text-sm text-muted-foreground">
                Every recovery request returns the same confirmation state, whether the account exists or not.
              </p>
            </div>
            <div className="rounded-2xl border border-border/70 bg-card/80 p-5 backdrop-blur">
              <p className="text-sm font-semibold text-foreground">Enrollment after sign-in</p>
              <p className="mt-2 text-sm text-muted-foreground">
                New operators can finish MFA setup inline, without leaving the dashboard flow.
              </p>
            </div>
          </div>
        </div>
        <div className="w-full lg:justify-self-end">
          <div className="rounded-[28px] border border-border/80 bg-card/90 p-6 shadow-2xl backdrop-blur sm:p-8">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
