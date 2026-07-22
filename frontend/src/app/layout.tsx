import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AppGate } from "@/components/shell/app-gate";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth/auth-context";

import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TMS AI Studio",
  description: "Plataforma interna de agentes de IA (ISDF) · Urbano TI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <AuthProvider>
          <TooltipProvider delay={200}>
            <AppGate>{children}</AppGate>
          </TooltipProvider>
          <Toaster position="top-right" />
        </AuthProvider>
      </body>
    </html>
  );
}
