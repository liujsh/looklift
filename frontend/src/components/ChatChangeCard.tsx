import type { ChatChange } from "../api/types";

const value = (item: unknown) => typeof item === "number" ? item.toFixed(2).replace(/\.00$/, "") : JSON.stringify(item);

export function ChatChangeCard({ changes }: { changes: readonly ChatChange[] }) {
  if (changes.length === 0) return null;
  return <section className="chat-change-card" aria-label="参数变化">
    <header><span>显影记录</span><strong>{changes.length} 项变化</strong></header>
    <ul>{changes.map((change) => <li key={change.path}>
      <code>{change.path}</code><span>{value(change.before)} → {value(change.after)}</span>
    </li>)}</ul>
  </section>;
}
