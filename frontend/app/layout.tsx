import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Revenue Recovery — Control Centre",
  description:
    "Operational control centre for the AI Revenue Recovery and Payment Intelligence platform.",
  // The dashboard shows tenant payment data; there is nothing here for a crawler.
  robots: { index: false, follow: false },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
