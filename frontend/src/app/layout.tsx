import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vid2Graph — turn videos into knowledge graphs",
  description: "Turn any educational video, podcast or technical interview into an interactive knowledge graph, locally.",
  icons: { icon: "/favicon.svg" },
};

const themeScript = `
(function(){try{var t=localStorage.getItem('v2g-theme');if(!t){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'}
document.documentElement.classList.toggle('dark',t==='dark')}catch(e){document.documentElement.classList.add('dark')}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="h-full antialiased">{children}</body>
    </html>
  );
}
