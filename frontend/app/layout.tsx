import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Codebase Explainer",
  description: "Onboard onto any GitHub repo in 30 seconds.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
