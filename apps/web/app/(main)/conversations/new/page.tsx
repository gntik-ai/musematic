export default function NewConversationPage() {
  return (
    <section className="space-y-4">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          Conversations
        </p>
        <h1 className="mt-2 text-3xl font-semibold">New conversation</h1>
      </div>
      <p className="max-w-2xl text-muted-foreground">
        Conversation drafting will be wired in a dedicated feature. This route
        exists so dashboard quick actions resolve to a valid surface.
      </p>
    </section>
  );
}
