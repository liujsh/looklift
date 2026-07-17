import { useState } from "react";
import { PANEL_GROUPS } from "../panel/groups";
import { useEditorState } from "../store/editorStore";

export function PanelPane() {
  const editor = useEditorState();
  const [openGroup, setOpenGroup] = useState<string>(PANEL_GROUPS[0].id);

  return (
    <aside className="panel-pane" data-pane="controls" aria-label="调整面板">
      <header className="pane-heading">
        <div>
          <p className="pane-kicker">编辑</p>
          <h2>调整</h2>
        </div>
        <button type="button" disabled={!editor.analysis}>重置</button>
      </header>

      <div className="strength-seam" data-control="factor">
        <span>整体强度</span>
        <strong>{Math.round(editor.factor * 100)}%</strong>
      </div>

      <nav className="panel-groups" aria-label="调整分组">
        {PANEL_GROUPS.map((group) => {
          const expanded = openGroup === group.id;
          return (
            <div className="panel-group" data-section={group.section} key={group.id}>
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpenGroup(expanded ? "" : group.id)}
              >
                <span>{group.label}</span>
                <span aria-hidden="true">{expanded ? "−" : "+"}</span>
              </button>
              {expanded && (
                <div className="group-content">
                  {editor.analysis
                    ? `${group.operators.length} 项参数`
                    : "载入分析结果后显示参数"}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="panel-note">
        {editor.imagePath
          ? editor.analysis ? "所有调整共享当前 analysis" : "等待分析结果回填参数"
          : "导入照片后显示参数控件"}
      </div>
    </aside>
  );
}
