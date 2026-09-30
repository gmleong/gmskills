import type { ReactNode } from "react";
import "./globals.css";

export const metadata = { title: "Terra Workshop · VibeDesign", description: "VibeDesign 真实业务对照案例" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
