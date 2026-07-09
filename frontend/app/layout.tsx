import React from "react";
import type { Metadata } from "next";
import { Space_Grotesk, Inter, Geist_Mono } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import { Providers } from "./providers";
import "./globals.css";

const _spaceGrotesk = Space_Grotesk({
    subsets: ["latin"],
    variable: "--font-heading",
});
const _inter = Inter({ subsets: ["latin"] });
const _geistMono = Geist_Mono({
    subsets: ["latin"],
    variable: "--font-mono",
});

export const metadata: Metadata = {
    title: "EduRot — Generate Short-Form Video at Scale",
    description:
        "Turn any source into a fully-voiced, captioned, edited short-form video. AI narration, precision timing, and instant export — built for creators who ship.",
    generator: "v0.app",
    icons: {
        icon: [
            {
                url: "/icon-light-32x32.png",
                media: "(prefers-color-scheme: light)",
            },
            {
                url: "/icon-dark-32x32.png",
                media: "(prefers-color-scheme: dark)",
            },
            {
                url: "/icon.svg",
                type: "image/svg+xml",
            },
        ],
        apple: "/apple-icon.png",
    },
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" className="dark">
            <body
                className={`font-sans antialiased ${_spaceGrotesk.variable} ${_geistMono.variable}`}
            >
                <Providers>{children}</Providers>
                <Analytics />
            </body>
        </html>
    );
}
