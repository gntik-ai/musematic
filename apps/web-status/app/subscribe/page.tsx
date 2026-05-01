import Link from "next/link";
import { SubscribeForm } from "@/components/SubscribeForm";

export default function SubscribePage() {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto grid w-full max-w-3xl gap-8 px-4 py-8">
        <header className="flex items-center justify-between gap-4">
          <Link href="/" className="text-lg font-semibold">
            Platform status
          </Link>
          <Link className="rounded-md border px-3 py-2 text-sm hover:bg-muted" href="/history/">
            History
          </Link>
        </header>
        <section className="grid gap-3">
          <h1 className="text-2xl font-semibold">Subscribe to updates</h1>
          <p className="text-sm text-muted-foreground">
            Choose email, webhook, or Slack notifications. RSS and Atom feeds are available below.
          </p>
        </section>
        <section className="rounded-md border bg-card p-4">
          <SubscribeForm />
        </section>
        <section className="rounded-md border bg-card p-4">
          <h2 className="text-lg font-semibold">Feeds</h2>
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <a className="rounded-md border px-3 py-2 hover:bg-muted" href="/api/v1/public/status/feed.rss">
              RSS feed
            </a>
            <a className="rounded-md border px-3 py-2 hover:bg-muted" href="/api/v1/public/status/feed.atom">
              Atom feed
            </a>
          </div>
        </section>
      </div>
    </main>
  );
}
