"use client";

export interface Decision {
  stage: string;
  verdict: "PASS" | "BLOCK" | "SKIP" | "INFO";
  reason: string;
  score: number | null;
  at: string;
}

const STAGE_NAMES: Record<string, string> = {
  market: "Market",
  strategy: "Strategy",
  ai_filter: "AI Filter",
  wiki_filter: "Wiki Filter",
  risk: "Risk Manager",
  execution: "Execution",
};

const VERDICT_STYLE: Record<Decision["verdict"], { dot: string; badge: string }> = {
  PASS: { dot: "bg-emerald-500", badge: "bg-emerald-950/40 text-emerald-400 border-emerald-900/50" },
  BLOCK: { dot: "bg-rose-500", badge: "bg-rose-950/40 text-rose-400 border-rose-900/50" },
  INFO: { dot: "bg-indigo-500", badge: "bg-indigo-950/40 text-indigo-400 border-indigo-900/50" },
  SKIP: { dot: "bg-gray-600", badge: "bg-gray-800/60 text-gray-400 border-gray-700" },
};

export function DecisionTree({ decisions }: { decisions: Decision[] }) {
  if (!decisions.length) {
    return <div className="text-xs text-gray-500">No decisions recorded.</div>;
  }
  return (
    <ol className="relative">
      {decisions.map((d, i) => {
        const style = VERDICT_STYLE[d.verdict];
        const last = i === decisions.length - 1;
        return (
          <li key={i} className="flex gap-3 pb-5 relative">
            {/* connector line */}
            {!last && (
              <span className="absolute left-[5px] top-4 bottom-0 w-px bg-gray-800" />
            )}
            <span className={`mt-1 h-[11px] w-[11px] rounded-full shrink-0 ${style.dot}`} />
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-gray-200">
                  {STAGE_NAMES[d.stage] ?? d.stage}
                </span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${style.badge}`}>
                  {d.verdict}
                </span>
                {d.score !== null && (
                  <span className="text-[10px] text-gray-500 font-mono">
                    score {(d.score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-0.5">{d.reason}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
