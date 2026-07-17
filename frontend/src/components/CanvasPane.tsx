export function CanvasPane() {
  return (
    <section className="canvas-pane" data-pane="canvas" aria-label="照片画布">
      <div className="canvas-toolbar" aria-label="画布工具">
        <span>适合窗口</span>
        <span>100%</span>
      </div>
      <div className="canvas-empty">
        <div className="drop-outline" aria-hidden="true">
          <span>＋</span>
        </div>
        <h1>把照片拖到这里</h1>
        <p>或点击选择文件 · JPEG、PNG、TIFF</p>
        <button type="button" disabled>选择照片</button>
      </div>
      <div className="canvas-footer" aria-hidden="true">
        <span>原图</span>
        <span className="diff-track"><i /></span>
        <span>效果</span>
      </div>
    </section>
  );
}
