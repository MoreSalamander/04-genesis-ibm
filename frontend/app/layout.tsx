import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Genesis OS — Enterprise Decision Intelligence",
  description:
    "The governance chamber — decision evaluation, policy findings, and human authorization (IBM track, Convergence Studios)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
