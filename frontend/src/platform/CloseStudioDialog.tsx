export type CloseDialogPhase = "ai" | "pending";

type CloseStudioDialogProps = {
  title: string;
  phase: CloseDialogPhase;
  busy: boolean;
  error?: string | null;
  onCancel(): void;
  onStop(): Promise<void> | void;
  onKeep(): Promise<void> | void;
  onDiscard(): Promise<void> | void;
};

export function CloseStudioDialog({
  title,
  phase,
  busy,
  error,
  onCancel,
  onStop,
  onKeep,
  onDiscard,
}: CloseStudioDialogProps) {
  return (
    <dialog className="close-studio-dialog" open aria-modal="true" aria-labelledby="close-studio-title">
      <div className="dialog-scrim" />
      <section>
        <p className="pane-kicker">关闭 Studio</p>
        <h2 id="close-studio-title">关闭 {title}？</h2>
        {phase === "ai" ? (
          <p>AI 请求仍在运行。停止后将继续检查是否存在待确认候选，再决定是否关闭。</p>
        ) : (
          <p>当前效果尚未成为正式版本。请选择保留、放弃，或返回继续比较。</p>
        )}
        {error && <p className="dialog-error" role="alert">{error}</p>}
        <footer>
          <button type="button" disabled={busy} onClick={onCancel}>取消</button>
          {phase === "ai" ? (
            <button className="danger" type="button" aria-label="停止并继续" disabled={busy} onClick={() => void onStop()}>
              {busy ? "正在停止…" : "停止并继续"}
            </button>
          ) : (
            <>
              <button className="danger" type="button" aria-label="放弃并关闭" disabled={busy} onClick={() => void onDiscard()}>
                放弃并关闭
              </button>
              <button className="primary" type="button" aria-label="保留并关闭" disabled={busy} onClick={() => void onKeep()}>
                {busy ? "正在保存…" : "保留并关闭"}
              </button>
            </>
          )}
        </footer>
      </section>
    </dialog>
  );
}
