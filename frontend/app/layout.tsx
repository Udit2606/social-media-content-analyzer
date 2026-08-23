import type { Metadata } from "next";
import { Inter, Inter_Tight } from "next/font/google";

import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";

import "./globals.css";

/** Body copy: high legibility at small sizes. */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

/**
 * Headlines: tighter and heavier than Inter, which is what gives the hero its
 * weight. Only the four weights actually used are loaded.
 */
const interTight = Inter_Tight({
  subsets: ["latin"],
  weight: ["600", "700", "800", "900"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "postpilot.ai — Social Media Content Analyzer",
  description:
    "Create. Optimize. Engage. Upload a PDF or image, extract the text, and get an engagement score with concrete suggestions for improving your post.",
};

/**
 * The root shell every page renders inside.
 *
 * Owns <html>/<body>, loads the stylesheet once, wires both font variables,
 * paints the ambient background, and places the header and footer so no
 * individual page has to remember them.
 */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${interTight.variable} font-sans antialiased`}
      >
        {/* Decorative only, so it is hidden from assistive tech and sits
            behind everything without affecting layout. */}
        <div aria-hidden="true" className="app-background fixed inset-0 -z-10" />

        <div className="flex min-h-dvh flex-col">
          <SiteHeader />
          <div className="flex-1">{children}</div>
          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
