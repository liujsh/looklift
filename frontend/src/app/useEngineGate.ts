import { useEffect, useState } from "react";
import { clientFromStatus, readSidecarStatus } from "../api/client";
import type { LookliftClient } from "../api/client";
import type { ParamContract, SidecarStatus } from "../api/types";

type EngineGate =
  | { phase: "starting"; error: null; numba: null; libvips: null }
  | { phase: "ready"; error: null; numba: string; libvips: string; client: LookliftClient; contract: ParamContract }
  | { phase: "error"; error: string; numba: null; libvips: null };

const STARTING: EngineGate = {
  phase: "starting",
  error: null,
  numba: null,
  libvips: null,
};

async function probeEngine(status: SidecarStatus): Promise<EngineGate> {
  const client = clientFromStatus(status);
  const [ping, probe, , contract] = await Promise.all([
    client.ping(),
    client.engineProbe(),
    client.listLooks(),
    client.paramContract(),
  ]);
  if (!ping.ok || !probe.rendered) throw new Error("本地引擎自检未通过");
  return {
    phase: "ready",
    error: null,
    numba: probe.numba,
    libvips: probe.libvips,
    client,
    contract,
  };
}

export function useEngineGate(): EngineGate {
  const [gate, setGate] = useState<EngineGate>(STARTING);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const status = await readSidecarStatus();
        if (cancelled) return;
        if (status.state === "error") throw new Error(status.error ?? "本地引擎启动失败");
        if (status.state === "ready") {
          const nextGate = await probeEngine(status);
          if (!cancelled) setGate(nextGate);
          return;
        }
        timer = window.setTimeout(poll, 250);
      } catch (reason) {
        if (!cancelled) {
          setGate({ phase: "error", error: String(reason), numba: null, libvips: null });
        }
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  return gate;
}
