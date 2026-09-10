import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "RailVox — Voice Railway Assistant",
  description:
    "Voice-native Indian railway search assistant with mid-flight correction and stale-result fencing. Built with Rime TTS.",
  keywords: [
    "voice assistant",
    "Indian railways",
    "Rime TTS",
    "LiveKit",
    "train search",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  );
}
