import type { Metadata } from "next";
import { Mona_Sans } from "next/font/google";
import "./globals.css";

import { ThemeProvider } from "@/components/layout/theme-provider";
import { SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { Header } from "@/components/layout/header";
import { Toaster } from "@/components/ui/sonner";

// Display face used by .page-title / .font-display in globals.css.
const monaSans = Mona_Sans({
  variable: "--font-display",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "nvidia-nemotron-genblaze-b2",
  description:
    "Drop in an image, audio clip, or short video. NVIDIA Nemotron 3 Nano Omni perceives it; Genblaze fans out to image, narration, and music generation; every artifact persists to Backblaze B2.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${monaSans.variable} antialiased`}>
        <ThemeProvider>
          <SidebarProvider>
            <TooltipProvider>
              <AppSidebar />
              <div className="flex flex-1 flex-col">
                <Header />
                <main className="flex-1 overflow-auto p-6 lg:p-8">{children}</main>
              </div>
              <Toaster richColors position="top-center" />
            </TooltipProvider>
          </SidebarProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
