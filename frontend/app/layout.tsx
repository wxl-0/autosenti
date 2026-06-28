import "./globals.css";

export const metadata = { title: "AutoSenti", description: "汽车竞品口碑情报分析" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="zh-CN"><body><main className="min-h-screen"><div className="p-4">{children}</div></main></body></html>;
}
