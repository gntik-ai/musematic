import { PreferencesForm } from "@/components/features/preferences";

export default function PreferencesPage() {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Preferences</h1>
        <p className="text-sm text-muted-foreground">
          Configure display, language, workspace, notifications, and export defaults.
        </p>
      </div>
      <PreferencesForm />
    </div>
  );
}
