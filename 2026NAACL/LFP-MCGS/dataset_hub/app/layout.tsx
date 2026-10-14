import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  title: "LFP-MCGS · Structured Test-Time Reasoning over Cyclic Documents",
  description:
    "The current LFP-MCGS framework: topology-controlled interventions on authority-backed document SCCs, source-grounded symbolic state, online LFP feedback, and matched-compute evaluation against general LLMs.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    title: "LFP-MCGS · Structured Test-Time Reasoning over Cyclic Documents",
    description: "Frozen document SCC → minimal seed/bridge/witness intervention → exact LFP feedback → matched-compute evaluation",
    type: "website",
    images: [
      {
        url: "/og.png",
        width: 1731,
        height: 909,
        alt: "LFP-MCGS research framework: cyclic document search, source-grounded knowledge, incremental closure, and test-time reasoning.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "LFP-MCGS · Structured Test-Time Reasoning over Cyclic Documents",
    description: "Frozen document SCC → minimal controlled intervention → exact LFP feedback → matched-compute evaluation",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
