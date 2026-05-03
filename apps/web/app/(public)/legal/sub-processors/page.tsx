import Link from "next/link";

export const revalidate = 300;

interface SubProcessorPublic {
  name: string;
  category: string;
  location: string;
  data_categories: string[];
  privacy_policy_url?: string | null;
  dpa_url?: string | null;
  started_using_at?: string | null;
}

interface PublicResponse {
  last_updated_at: string;
  items: SubProcessorPublic[];
}

async function loadSubProcessors(): Promise<PublicResponse> {
  const baseUrl =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${baseUrl}/api/v1/public/sub-processors`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) {
    throw new Error(`Failed to load sub-processors: ${res.status}`);
  }
  return (await res.json()) as PublicResponse;
}

export default async function PublicSubProcessorsPage() {
  let payload: PublicResponse;
  try {
    payload = await loadSubProcessors();
  } catch {
    payload = { last_updated_at: new Date().toISOString(), items: [] };
  }
  const lastUpdated = new Date(payload.last_updated_at);

  return (
    <article className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Sub-processors</h1>
        <p className="text-sm text-muted-foreground">
          The third-party services we rely on to operate Musematic. Last
          updated {lastUpdated.toLocaleDateString()}.
        </p>
        <div className="text-xs text-muted-foreground">
          Subscribe to changes:{" "}
          <Link
            href="/api/v1/public/sub-processors.rss"
            className="underline hover:text-foreground"
          >
            RSS feed
          </Link>{" "}
          ·{" "}
          <Link href="/legal/sub-processors/subscribe" className="underline hover:text-foreground">
            Email notifications
          </Link>
        </div>
      </header>

      <section className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-3">Sub-processor</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Location</th>
              <th className="px-4 py-3">Data categories</th>
              <th className="px-4 py-3">Policies</th>
            </tr>
          </thead>
          <tbody>
            {payload.items.map((item) => (
              <tr key={item.name} className="border-t">
                <td className="px-4 py-3 font-medium">{item.name}</td>
                <td className="px-4 py-3 text-muted-foreground">{item.category}</td>
                <td className="px-4 py-3 text-muted-foreground">{item.location}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {item.data_categories.join(", ")}
                </td>
                <td className="px-4 py-3 text-xs">
                  {item.privacy_policy_url ? (
                    <a
                      href={item.privacy_policy_url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline hover:text-foreground"
                    >
                      Privacy
                    </a>
                  ) : null}
                  {item.dpa_url ? (
                    <>
                      {" · "}
                      <a
                        href={item.dpa_url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline hover:text-foreground"
                      >
                        DPA
                      </a>
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
            {payload.items.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-center text-muted-foreground" colSpan={5}>
                  Sub-processor list is currently being refreshed.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </article>
  );
}
