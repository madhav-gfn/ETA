import type { Metadata } from "next";
// UX4G (India's government design system, NeGD/MeitY) tokens + components,
// loaded before globals.css so Tailwind utilities win specificity ties.
import "ux4g-web-components/styles.css";
import "./globals.css";
import AppShell from "@/components/AppShell";

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
    <html lang="en">
      <body className="min-h-screen bg-neutral-50 font-sans text-neutral-900 antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
