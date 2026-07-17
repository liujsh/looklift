const PANEL_GROUPS = ["基础", "色彩", "HSL", "曲线", "分级", "效果"];

export function PanelPane() {
  return (
    <aside className="panel-pane" data-pane="controls" aria-label="调整面板">
      <header className="pane-heading">
        <div>
          <p className="pane-kicker">编辑</p>
          <h2>调整</h2>
        </div>
        <button type="button" disabled>重置</button>
      </header>
      <nav className="panel-groups" aria-label="调整分组">
        {PANEL_GROUPS.map((group, index) => (
          <button type="button" key={group} aria-expanded={index === 0} disabled>
            <span>{group}</span>
            <span aria-hidden="true">{index === 0 ? "−" : "+"}</span>
          </button>
        ))}
      </nav>
      <div className="panel-note">导入照片后显示参数控件</div>
    </aside>
  );
}
