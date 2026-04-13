import type { Metadata } from "next";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { WebSocketProvider } from "@/components/providers/WebSocketProvider";
import { Toaster } from "@/components/ui/toaster";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Musematic Agentic Mesh",
  description: "Operational frontend scaffold for the Agentic Mesh Platform.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <ThemeProvider>
          <QueryProvider>
            <WebSocketProvider>
              {children}
              <Toaster />
            </WebSocketProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
