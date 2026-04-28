import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Musematic Platform Status",
  description: "Current platform status and incident history for Musematic.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
