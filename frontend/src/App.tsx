import { useMemo } from "react";
import { EditorShell } from "./app/EditorShell";
import { useEngineGate } from "./app/useEngineGate";
import { createEditorStore } from "./store/editorStore";
import "./App.css";

function App() {
  const engine = useEngineGate();
  const store = useMemo(() => createEditorStore(), []);

  if (engine.phase !== "ready") {
    return (
      <main className="startup-shell" aria-live="polite">
        <section className="startup-card">
          <p className="eyebrow">looklift desktop</p>
          <h1>正在准备暗房</h1>
          <p>{engine.phase === "error" ? engine.error : "正在连接本地调色引擎…"}</p>
          <span className="startup-progress" aria-hidden="true" />
        </section>
      </main>
    );
  }

  return (
    <EditorShell
      store={store}
      client={engine.client}
      contract={engine.contract}
      engineLabel={`${engine.numba} · libvips ${engine.libvips}`}
    />
  );
}

export default App;
