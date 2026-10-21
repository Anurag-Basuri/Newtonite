import "./globals.css";
import { Schibsted_Grotesk, JetBrains_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
const sans = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });
export const metadata = { title: "Opsboard" };
export default function Root({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
