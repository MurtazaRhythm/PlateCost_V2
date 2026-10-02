import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PlateCost",
  description: "Photograph a restaurant receipt and PlateCost files the expense.",
  applicationName: "PlateCost",
  appleWebApp: { capable: true, title: "PlateCost", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f3f1ec",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geist.variable} h-full antialiased`}>
      <body className="min-h-dvh bg-[#e7e2d8] text-foreground">
        <div className="mx-auto min-h-dvh w-full max-w-md bg-background shadow-xl">{children}</div>
      </body>
    </html>
  );
}
