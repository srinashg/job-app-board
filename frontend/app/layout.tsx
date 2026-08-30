import type { Metadata } from "next";

import { Nav } from "@/components/Nav";
import { AuthProvider } from "@/lib/auth";

import "./globals.css";

export const metadata: Metadata = {
  title: "Job Application Board",
  description:
    "Five relevant jobs at a time. Apply, skip with a reason, or mark unavailable to unlock the next set.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <div className="app-shell">
            <Nav />
            <main>{children}</main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
