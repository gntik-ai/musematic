import Link from "next/link";

export default function PublicLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            Musematic
          </Link>
          <nav className="text-xs text-muted-foreground">
            <Link href="/legal/sub-processors" className="hover:text-foreground">
              Sub-processors
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-12">{children}</main>
      <footer className="mx-auto max-w-5xl px-6 py-8 text-xs text-muted-foreground">
        © {new Date().getFullYear()} Musematic. All rights reserved.
      </footer>
    </div>
  );
}
