import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ForgeGuard — Predictive Maintenance Command Center",
  description:
    "Cost-aware predictive maintenance for manufacturing operations. Rank at-risk machinery, tune alert thresholds, and allocate technician shifts.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-background text-foreground min-h-screen antialiased selection:bg-accent-forest-subtle selection:text-foreground">
        {children}
      </body>
    </html>
  );
}
