import type { Analysis } from "../api/types";

export function AnalysisBrief({ analysis }: { analysis: Analysis }) {
  if (!analysis.summary && analysis.steps.length === 0) return null;
  return (
    <section className="analysis-brief" aria-label="AI 分析说明">
      {analysis.summary && <p>{analysis.summary}</p>}
      {analysis.steps.length > 0 && (
        <ol>{analysis.steps.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol>
      )}
    </section>
  );
}
