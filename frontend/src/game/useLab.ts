// Game state on top of the authoritative backend. Every change of stage, evidence,
// balance or grade comes from an API response; the client only serializes requests and
// discards responses that belong to an experiment that has since been reset.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, forgetLabVersion, lab } from "../api";
import type { EvidenceItem, Mission, Result, Session } from "../api";

export type Busy =
  | "load"
  | "start"
  | "inspect"
  | "hint"
  | "choose"
  | "replay"
  | "reset"
  | "report"
  | null;
export interface LabError {
  message: string;
  code: string;
  recover: "reload" | "refresh" | "start" | "dismiss";
}

export interface LabState {
  mission: Mission | null;
  session: Session | null;
  evidence: Record<string, EvidenceItem>;
  result: Result | null;
  lastHint: string | null;
  busy: Busy;
  error: LabError | null;
  loaded: boolean;
  /** Increments each time a new case is opened in this tab. */
  cases: number;
}

function describe(error: unknown): LabError {
  if (error instanceof ApiError) {
    if (error.code === "stale-state")
      return {
        code: error.code,
        message: "实验状态已在别处更新，已同步到最新状态。请再操作一次。",
        recover: "dismiss",
      };
    if (error.code === "no-session")
      return {
        code: error.code,
        message: "这次调查已不存在（服务可能重启过）。请重新开始调查。",
        recover: "start",
      };
    if (error.status === 503)
      return {
        code: error.code,
        message: `本地链没有就绪：${error.message}`,
        recover: "reload",
      };
    if (error.code === "network" || error.status === 0)
      return { code: "network", message: error.message, recover: "reload" };
    return { code: error.code, message: error.message, recover: "refresh" };
  }
  return {
    code: "network",
    message: `无法连接本地实验服务：${String(error)}`,
    recover: "reload",
  };
}

export function useLab() {
  const [state, setState] = useState<LabState>({
    mission: null,
    session: null,
    evidence: {},
    result: null,
    lastHint: null,
    busy: "load",
    error: null,
    loaded: false,
    cases: 0,
  });
  const lock = useRef(false);
  const epoch = useRef(0);

  const patch = useCallback(
    (change: Partial<LabState>) => setState((old) => ({ ...old, ...change })),
    [],
  );

  /** Run one backend action at a time; later calls while busy are ignored. */
  const run = useCallback(
    async (
      busy: Exclude<Busy, null>,
      work: (current: number) => Promise<void>,
    ) => {
      if (lock.current) return;
      lock.current = true;
      const current = epoch.current;
      patch({ busy, error: null });
      try {
        await work(current);
      } catch (error) {
        const failure = describe(error);
        patch({ error: failure });
        if (failure.code === "stale-state" || failure.recover === "refresh") {
          try {
            const session = await lab.session();
            if (epoch.current === current)
              patch({ session, result: session.result });
          } catch {
            /* keep what is on screen; the error offers a retry */
          }
        }
        if (failure.code === "no-session")
          patch({ session: null, result: null, evidence: {} });
      } finally {
        lock.current = false;
        patch({ busy: null });
      }
    },
    [patch],
  );

  const load = useCallback(
    () =>
      run("load", async () => {
        const mission = await lab.mission();
        let session: Session | null = null;
        try {
          session = await lab.session();
        } catch (error) {
          if (!(error instanceof ApiError && error.code === "no-session"))
            throw error;
        }
        const evidence: Record<string, EvidenceItem> = {};
        // Resuming: re-open evidence the backend says was already inspected (no new events).
        for (const item of session?.evidence ?? []) {
          if (item.inspected) evidence[item.id] = await lab.inspect(item.id);
        }
        patch({
          mission,
          session,
          evidence,
          result: session?.result ?? null,
          loaded: true,
        });
      }).finally(() => patch({ loaded: true })),
    [run, patch],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const start = useCallback(
    () =>
      run("start", async () => {
        epoch.current += 1;
        forgetLabVersion();
        const session = await lab.start();
        setState((old) => ({
          ...old,
          session,
          evidence: {},
          result: null,
          lastHint: null,
          cases: old.cases + 1,
        }));
      }),
    [run, patch],
  );

  const inspect = useCallback(
    (id: string) =>
      run("inspect", async (current) => {
        const item = await lab.inspect(id);
        const session = await lab.session();
        if (epoch.current !== current) return;
        setState((old) => ({
          ...old,
          evidence: { ...old.evidence, [id]: item },
          session,
        }));
      }),
    [run],
  );

  const hint = useCallback(
    () =>
      run("hint", async (current) => {
        const next = await lab.hint();
        const session = await lab.session();
        if (epoch.current === current) patch({ lastHint: next.text, session });
      }),
    [run, patch],
  );

  const choose = useCallback(
    (choice: string) =>
      run("choose", async (current) => {
        const session = await lab.choose(choice);
        if (epoch.current === current) patch({ session });
      }),
    [run, patch],
  );

  const replay = useCallback(
    () =>
      run("replay", async (current) => {
        const result = await lab.replay();
        if (epoch.current !== current) return;
        patch({ result });
        const session = await lab.session();
        if (epoch.current === current)
          patch({ session, result: session.result ?? result });
      }),
    [run, patch],
  );

  // One UI gesture, two authoritative actions. A failed choice must never fall
  // through to replay; keep both inside the same error boundary and busy lock.
  const experiment = useCallback(
    (choice: string) =>
      run("replay", async (current) => {
        const chosen = await lab.choose(choice);
        if (epoch.current !== current) return;
        patch({ session: chosen });
        const result = await lab.replay();
        if (epoch.current !== current) return;
        patch({ result });
        const session = await lab.session();
        if (epoch.current === current)
          patch({ session, result: session.result ?? result });
      }),
    [run, patch],
  );

  const accept = useCallback(
    () =>
      run("start", async () => {
        epoch.current += 1;
        const current = epoch.current;
        forgetLabVersion();
        const session = await lab.start();
        setState((old) => ({
          ...old,
          session,
          evidence: {},
          result: null,
          lastHint: null,
          cases: old.cases + 1,
        }));
        const item = await lab.inspect("authorized-intent");
        const updated = await lab.session();
        if (epoch.current === current)
          patch({ evidence: { "authorized-intent": item }, session: updated });
      }),
    [run, patch],
  );

  const reset = useCallback(
    () =>
      run("reset", async () => {
        epoch.current += 1;
        const session = await lab.reset();
        patch({ session, result: null });
      }),
    [run, patch],
  );

  const report = useCallback(
    () =>
      run("report", async () => {
        const data = await lab.report();
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "genesis-wrong-recipient-report.json";
        link.click();
        URL.revokeObjectURL(url);
      }),
    [run],
  );

  const dismissError = useCallback(() => patch({ error: null }), [patch]);
  const dismissHint = useCallback(() => patch({ lastHint: null }), [patch]);

  return {
    ...state,
    load,
    start,
    accept,
    inspect,
    hint,
    choose,
    replay,
    experiment,
    reset,
    report,
    dismissError,
    dismissHint,
  };
}

export type Lab = ReturnType<typeof useLab>;
