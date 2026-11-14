import type { Metadata, Viewport } from "next";
import { Source_Sans_3 } from "next/font/google";
import { CommandBar } from "@/components/CommandBar";
import { TabBar } from "@/components/TabBar";
import { WarmUp } from "@/components/WarmUp";
import "./globals.css";

const text = Source_Sans_3({ variable: "--font-text", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FINN",
  description: "A daily briefing on your portfolio: what changed, so what, who can help.",
  appleWebApp: { capable: true, title: "FINN", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfaf8" },
    { media: "(prefers-color-scheme: dark)", color: "#0f0f12" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className={`${text.variable} h-full antialiased`}>
      <body className="min-h-full">
        <WarmUp />
        {/* Designed at 390 px; on desktop a centred phone-width column. */}
        <div className="mx-auto flex min-h-dvh w-full max-w-[480px] flex-col border-line md:border-x">
          <main className="flex-1 px-4 pb-40 pt-[max(env(safe-area-inset-top),16px)]">
            {children}
          </main>
          <div className="fixed inset-x-0 bottom-0 z-10">
            <div className="mx-auto w-full max-w-[480px] border-t border-line bg-bg/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
              <CommandBar />
              <TabBar />
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
