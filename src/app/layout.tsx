import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PartSelect Parts Assistant | AI-Powered Help for Refrigerator & Dishwasher Parts",
  description: "Get instant help finding, installing, and troubleshooting refrigerator and dishwasher parts. AI-powered assistant by PartSelect.",
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
