"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { name: "Dashboard", path: "/" },
  { name: "Backtest", path: "/backtest" },
  { name: "Live", path: "/live" },
  { name: "History", path: "/history" },
  { name: "Review", path: "/review" },
  { name: "Money Mgmt", path: "/money-mgt" },
  { name: "Journal", path: "/journal" },
  { name: "Settings", path: "/settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-60 h-screen bg-[#0a0d12] border-r border-gray-800 flex flex-col">
      <button
        onClick={() => window.location.reload()}
        title="Click to refresh"
        aria-label="Refresh"
        className="group relative block w-full border-b border-gray-800 p-3 hover:bg-gray-900/40 transition focus:outline-none"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="IntelliTrade" className="w-full h-auto rounded-md block" />
        <span className="absolute inset-0 hidden group-hover:flex items-center justify-center gap-1 bg-black/55 text-white text-xs font-semibold backdrop-blur-[1px]">
          ↻ Refresh
        </span>
      </button>
      <nav className="p-3 space-y-1 flex-1">
        {NAV.map((item) => {
          const active = pathname === item.path;
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`block px-4 py-2.5 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-gray-800 text-amber-400 font-semibold"
                  : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
              }`}
            >
              {item.name}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-800 text-[11px] text-gray-500">
        MT5 Client Proxy
      </div>
    </aside>
  );
}
