// Shared loading state. Cold-start on a free dyno can take 30s; the
// previous one-line "loading…" in 40% white was easy to mistake for
// a blank page. This shows a clear spinner + helpful copy.

export function LoadingScreen({
  label = "loading…",
  hint,
}: {
  label?: string;
  hint?: string;
}) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="w-10 h-10 rounded-full border-4 border-white/15 border-t-white/70 animate-spin" />
      <div className="text-white/80">{label}</div>
      {hint && <div className="text-xs text-white/50 max-w-xs">{hint}</div>}
    </div>
  );
}
