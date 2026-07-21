import { useEngineGate } from "./app/useEngineGate";
import { PlatformShell } from "./platform/PlatformShell";
import "./App.css";

function App() {
  const engine = useEngineGate();

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
    <PlatformShell
      client={engine.client}
      contract={engine.contract}
      engineLabel={`${engine.numba} · libvips ${engine.libvips}`}
    />
  );
}

export default App;
