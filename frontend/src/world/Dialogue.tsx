import { useEffect, useState } from "react";

/** Small, skippable story beats. API actions stay directly accessible. */
export function Dialogue({ lines }: { lines: readonly string[] }) {
  const [page, setPage] = useState(0);
  const next = () => setPage((old) => (old + 1) % Math.max(1, lines.length));
  useEffect(() => {
    const advance = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (
        event.repeat ||
        event.defaultPrevented ||
        target?.closest("input,textarea,select,[contenteditable]")
      )
        return;
      // Enter on a button retains its normal action (including the next button).
      if (
        event.key.toLowerCase() === "e" ||
        (event.key === "Enter" && !target?.closest("button,a,summary"))
      ) {
        event.preventDefault();
        next();
      }
    };
    window.addEventListener("keydown", advance);
    return () => window.removeEventListener("keydown", advance);
  }, [lines.length]);
  return (
    <div className="dialogue-beat">
      <p className="world-dialogue" aria-live="polite">
        {lines[page] ?? lines[0]}
      </p>
      {lines.length > 1 && (
        <div className="dialogue-pagination">
          <span aria-label="对话进度">
            {page + 1} / {lines.length}
          </span>
          <button data-dialogue-next onClick={next}>
            {page + 1 === lines.length ? "再听一遍" : "下一句"}{" "}
            <kbd>E / Enter</kbd>
          </button>
        </div>
      )}
    </div>
  );
}
