"use client";

export function TypingIndicator() {
  return (
    <div
      aria-label="Agent is typing"
      aria-live="polite"
      className="flex items-center gap-1 rounded-full bg-muted px-3 py-2 text-muted-foreground"
    >
      <span className="sr-only">Agent is typing</span>
      <span className="h-2 w-2 rounded-full bg-current animate-bounce" />
      <span
        className="h-2 w-2 rounded-full bg-current animate-bounce"
        style={{ animationDelay: "100ms" }}
      />
      <span
        className="h-2 w-2 rounded-full bg-current animate-bounce"
        style={{ animationDelay: "200ms" }}
      />
    </div>
  );
}
