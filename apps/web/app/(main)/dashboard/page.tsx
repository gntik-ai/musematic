export default function DashboardRoutePage() {
  return (
    <section className="space-y-4">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          Overview
        </p>
        <h1 className="mt-2 text-3xl font-semibold">Mission control dashboard</h1>
      </div>
      <p className="max-w-2xl text-muted-foreground">
        The scaffold is ready for bounded-context features. Use the sidebar, command palette,
        and component showcase to validate the foundation before wiring live backend workflows.
      </p>
    </section>
  );
}
