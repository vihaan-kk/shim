import type { Metadata } from "next";
import { Instrument_Sans, Instrument_Serif, JetBrains_Mono } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppShell } from "@/components/app-shell";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Shim Workbench",
  description:
    "Measurement-driven demonstration socket: residual limb, socket shell and a confirmed virtual print, with one agent across all three pages.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${instrumentSans.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="h-dvh overflow-hidden flex flex-col">
        <TooltipProvider>
          <SessionProvider>
            <AppShell>{children}</AppShell>
          </SessionProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
