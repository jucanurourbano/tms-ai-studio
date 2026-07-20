import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AppSidebar } from "@/components/app-sidebar";
import { Toaster } from "@/components/ui/sonner";

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
        <div className="flex h-screen">
          <AppSidebar />
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
        <Toaster position="top-right" />
      </body>
    </html>
  );
}
