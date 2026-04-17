"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type FeedItem = {
  timestamp?: string;
  action?: string;
  company?: string | null;
  title?: string | null;
  status?: string;
  details?: Record<string, unknown>;
};

export function LiveFeed() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [connected, setConnected] = useState(false);

  const url = useMemo(() => `${API_BASE}/events`, []);

  useEffect(() => {
    const source = new EventSource(url);

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    const handler = (event: MessageEvent<string>) => {
      if (!event.data || event.data === "{}") return;
      try {
        const payload = JSON.parse(event.data) as FeedItem;
        setItems((prev) => [payload, ...prev].slice(0, 50));
      } catch {
        /* ignore malformed chunks */
      }
    };

    source.addEventListener("jobpilot", handler as EventListener);
    return () => {
      source.removeEventListener("jobpilot", handler as EventListener);
      source.close();
    };
  }, [url]);

  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">Live orchestration feed</p>
          <p className="text-xs text-slate-500">Listening to {url}</p>
        </div>
        <span
          className={`rounded-full px-2 py-1 text-xs font-medium ${
            connected ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
          }`}
        >
          {connected ? "Connected" : "Reconnecting…"}
        </span>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">Waiting for events from the JobPilot API…</p>
        ) : (
          items.map((item, idx) => (
            <div key={`${item.timestamp ?? idx}-${item.action}`} className="rounded-lg bg-slate-50 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold text-slate-900">{item.action ?? "event"}</p>
                <span className="text-xs uppercase text-slate-500">{item.status}</span>
              </div>
              <p className="text-xs text-slate-500">{item.timestamp}</p>
              {item.details ? (
                <pre className="mt-2 max-h-32 overflow-auto rounded bg-white p-2 text-xs text-slate-700">
                  {JSON.stringify(item.details, null, 2)}
                </pre>
              ) : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
