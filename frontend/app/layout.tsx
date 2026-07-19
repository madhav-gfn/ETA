import type { Metadata } from "next";
import { Inter } from "next/font/google";
// Base component primitives (buttons, alerts, progress bars, tables) come
// from ux4g-web-components; loaded before globals.css so Tailwind utilities
// win specificity ties. The library ships a first-class dark theme activated
// via data-theme="dark" below — visual branding on top is fully custom.
import "ux4g-web-components/styles.css";
import "./globals.css";
import AppShell from "@/components/AppShell";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: {
    default: "UrbanAir Intel — Urban Air Quality Intelligence",
    template: "%s · UrbanAir Intel",
  },
  description:
    "AI-powered urban air quality intelligence: hyperlocal forecasting, source attribution, enforcement dispatch and citizen advisories for Indian smart cities.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="dark" className={inter.variable}>
      <body className="min-h-screen bg-neutral-50 font-sans text-neutral-900 antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
