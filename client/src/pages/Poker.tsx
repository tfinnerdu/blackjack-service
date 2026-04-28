import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { CardChips, CardPicker } from "../components/poker/CardPicker";
import { ApiError } from "../lib/api";
import {
  CompanionAnalysisView,
  EquityResult,
  Poker,
  VariantSpec,
} from "../lib/poker";

type Slot = "cards" | "hole" | "board";

type VariantWithMeta = VariantSpec & { _saved_template_id?: number };

export default function PokerPage() {
  const [variants, setVariants] = useState<VariantWithMeta[]>([]);
  const [variantName, setVariantName] = useState<string | null>(null);
  const [hole, setHole] = useState<string[]>([]);
  const [board, setBoard] = useState<string[]>([]);
  const [cards, setCards] = useState<string[]>([]);
  const [activeSlot, setActiveSlot] = useState<Slot>("cards");
  const [analysis, setAnalysis] = useState<CompanionAnalysisView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorJson, setEditorJson] = useState("");
  const [editorError, setEditorError] = useState<string | null>(null);
  const [wildMode, setWildMode] = useState(false);
  const [wildIndices, setWildIndices] = useState<number[]>([]);
  const [opponents, setOpponents] = useState(1);
  const [equity, setEquity] = useState<EquityResult | null>(null);
  const [equityBusy, setEquityBusy] = useState(false);
  const [equityError, setEquityError] = useState<string | null>(null);

  function toggleWildIdx(idx: number) {
    setWildIndices((ws) =>
      ws.includes(idx) ? ws.filter((i) => i !== idx) : [...ws, idx],
    );
  }

  useEffect(() => {
    Poker.variants()
      .then((d) => {
        setVariants(d.variants);
        setVariantName(d.variants[0]?.name ?? null);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const variant = useMemo(
    () => variants.find((v) => v.name === variantName) ?? null,
    [variants, variantName],
  );

  function refreshVariants() {
    return Poker.variants()
      .then((d) => setVariants(d.variants))
      .catch((e) => setError(String(e)));
  }

  function openEditorClone() {
    if (!variant) return;
    const clone = { ...variant, name: `${variant.name} (copy)` };
    delete (clone as VariantWithMeta)._saved_template_id;
    setEditorJson(JSON.stringify(clone, null, 2));
    setEditorError(null);
    setEditorOpen(true);
  }

  function openEditorBlank() {
    setEditorJson(JSON.stringify({
      name: "My Custom Variant",
      description: "",
      family: "home",
      deck: { decks: 1, jokers: 1 },
      deal: {
        hole_cards: 5, up_cards: 0,
        community_streets: [], stud_streets: [],
        stud_face_down_final: false, draws: [],
      },
      wilds: [{ kind: "joker", mode: "fully_wild" }],
      hand: "exactly_5_hole",
      hi_lo: "hi_only",
      lo_rule: null,
      lo_eight_or_better: false,
      notes: "",
    }, null, 2));
    setEditorError(null);
    setEditorOpen(true);
  }

  async function saveEditor() {
    let parsed: VariantSpec;
    try {
      parsed = JSON.parse(editorJson);
    } catch {
      setEditorError("invalid JSON");
      return;
    }
    try {
      const saved = await Poker.saveVariant(parsed);
      await refreshVariants();
      setVariantName(saved.name);
      setEditorOpen(false);
    } catch (e) {
      setEditorError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  }

  async function deleteSelectedVariant() {
    if (!variant?._saved_template_id) return;
    if (!confirm(`Delete "${variant.name}"?`)) return;
    await Poker.deleteVariant(variant._saved_template_id);
    await refreshVariants();
    setVariantName("Texas Hold'em");
  }

  const isOmaha = variant?.hand === "omaha_2_hole_3_board";
  const jokersAllowed = (variant?.deck.jokers ?? 0) > 0;

  // Switch active slot defaults when the variant changes; reset wilds.
  useEffect(() => {
    if (!variant) return;
    setActiveSlot(isOmaha ? "hole" : "cards");
    setAnalysis(null);
    setError(null);
    setWildIndices([]);
    setWildMode(false);
  }, [variant, isOmaha]);

  function add(token: string) {
    if (activeSlot === "hole") setHole((h) => [...h, token]);
    else if (activeSlot === "board") setBoard((b) => [...b, token]);
    else setCards((c) => [...c, token]);
  }

  function addJoker(big: boolean) {
    add(big ? "JK" : "jk");
  }

  function remove(slot: Slot, index: number) {
    if (slot === "hole") setHole((h) => h.filter((_, i) => i !== index));
    else if (slot === "board") setBoard((b) => b.filter((_, i) => i !== index));
    else setCards((c) => c.filter((_, i) => i !== index));
  }

  function clearAll() {
    setHole([]);
    setBoard([]);
    setCards([]);
    setWildIndices([]);
    setWildMode(false);
    setAnalysis(null);
    setError(null);
  }

  async function runEquity() {
    if (!variant) return;
    setEquityBusy(true);
    setEquityError(null);
    setEquity(null);
    try {
      const result = await Poker.equity(
        isOmaha
          ? { variant: variant.name, hole, board, opponents, iterations: 2000 }
          : {
              variant: variant.name,
              // Map flat 'cards' to hole + board: assume the FIRST n_hole are
              // hero's hole and the rest are the visible board. Hold'em uses
              // 2; other community variants set their own hole_cards count.
              hole: cards.slice(0, variant.deal.hole_cards),
              board: cards.slice(variant.deal.hole_cards),
              opponents,
              iterations: 2000,
            },
      );
      setEquity(result);
    } catch (e) {
      setEquityError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setEquityBusy(false);
    }
  }

  async function analyze() {
    if (!variant) return;
    setBusy(true);
    setError(null);
    try {
      const result = await Poker.analyze(
        isOmaha
          ? {
              variant: variant.name,
              hole, board,
              wild_indices: wildIndices.length ? wildIndices : undefined,
            }
          : {
              variant: variant.name,
              cards,
              wild_indices: wildIndices.length ? wildIndices : undefined,
            },
      );
      setAnalysis(result);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="min-h-screen px-4 py-4"
      style={{
        paddingTop: "calc(env(safe-area-inset-top) + 12px)",
        paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)",
      }}
    >
      <div className="max-w-md mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <Link to="/" className="text-white/60 text-sm">
            ←
          </Link>
          <Link to="/poker/sim/setup" className="text-xs text-white/60 underline">
            Try the simulator →
          </Link>
        </div>

        <div>
          <label className="block">
            <div className="text-xs uppercase tracking-wide text-white/60 mb-1">
              Variant
            </div>
            <select
              className="w-full min-h-touch rounded-xl bg-felt px-3 text-white"
              value={variantName ?? ""}
              onChange={(e) => setVariantName(e.target.value)}
            >
              {variants.map((v) => (
                <option key={v.name} value={v.name}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          {variant && (
            <p className="text-xs text-white/60 mt-2">{variant.description}</p>
          )}
          {variant && variant.notes && (
            <p className="text-xs text-amber-200/70 mt-1">{variant.notes}</p>
          )}
          <div className="grid grid-cols-3 gap-2 mt-3">
            <button
              onClick={openEditorBlank}
              className="min-h-touch rounded-lg border border-white/20 text-xs"
            >
              + New
            </button>
            <button
              onClick={openEditorClone}
              disabled={!variant}
              className="min-h-touch rounded-lg border border-white/20 text-xs disabled:opacity-40"
            >
              Clone
            </button>
            <button
              onClick={deleteSelectedVariant}
              disabled={!variant?._saved_template_id}
              className="min-h-touch rounded-lg border border-red-300/40 text-red-200 text-xs disabled:opacity-30"
            >
              Delete
            </button>
          </div>
        </div>

        {/* Slot tabs (Omaha) or single slot (everything else) */}
        {isOmaha ? (
          <div className="grid grid-cols-2 gap-2">
            {(["hole", "board"] as const).map((slot) => (
              <button
                key={slot}
                onClick={() => setActiveSlot(slot)}
                className={`min-h-touch rounded-xl ${
                  activeSlot === slot
                    ? "bg-white text-felt-dark font-semibold"
                    : "border border-white/20"
                }`}
              >
                {slot === "hole" ? "Your 4 hole" : "Board"}
              </button>
            ))}
          </div>
        ) : null}

        {isOmaha ? (
          <>
            <SlotBlock
              label="Hole (4)"
              cards={hole}
              onRemove={(i) => remove("hole", i)}
              onToggleWild={(i) => toggleWildIdx(i)}
              wildIndices={wildIndices.filter((wi) => wi < hole.length)}
              wildMode={wildMode}
              isActive={activeSlot === "hole"}
            />
            <SlotBlock
              label="Board"
              cards={board}
              onRemove={(i) => remove("board", i)}
              onToggleWild={(i) => toggleWildIdx(hole.length + i)}
              wildIndices={wildIndices
                .filter((wi) => wi >= hole.length)
                .map((wi) => wi - hole.length)}
              wildMode={wildMode}
              isActive={activeSlot === "board"}
            />
          </>
        ) : (
          <SlotBlock
            label="Your cards"
            cards={cards}
            onRemove={(i) => remove("cards", i)}
            onToggleWild={(i) => toggleWildIdx(i)}
            wildIndices={wildIndices}
            wildMode={wildMode}
            isActive
          />
        )}

        <button
          onClick={() => setWildMode((w) => !w)}
          className={`w-full min-h-touch rounded-xl text-sm font-semibold ${
            wildMode
              ? "bg-amber-500/30 text-amber-100 ring-1 ring-amber-400"
              : "border border-white/20 text-white/70"
          }`}
        >
          {wildMode
            ? `Wild marking on (${wildIndices.length}) — tap a chip to toggle`
            : "Mark cards wild for this hand…"}
        </button>

        {!wildMode && (
          <div className="rounded-xl bg-felt p-3">
            <CardPicker
              onAdd={add}
              onAddJoker={addJoker}
              jokersAllowed={jokersAllowed}
            />
          </div>
        )}

        {error && <div className="text-red-300 text-sm">{error}</div>}

        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={clearAll}
            className="min-h-touch rounded-xl border border-white/20"
          >
            Clear
          </button>
          <button
            onClick={analyze}
            disabled={busy || !variant}
            className="min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
          >
            {busy ? "…" : "Analyze"}
          </button>
        </div>

        {analysis && <AnalysisView a={analysis} />}

        <EquityPanel
          opponents={opponents}
          setOpponents={setOpponents}
          equity={equity}
          busy={equityBusy}
          error={equityError}
          onRun={runEquity}
          variant={variant}
        />
      </div>

      {editorOpen && (
        <VariantEditorSheet
          json={editorJson}
          onJsonChange={setEditorJson}
          onSave={saveEditor}
          onClose={() => setEditorOpen(false)}
          error={editorError}
        />
      )}
    </div>
  );
}

function VariantEditorSheet({
  json,
  onJsonChange,
  onSave,
  onClose,
  error,
}: {
  json: string;
  onJsonChange: (s: string) => void;
  onSave: () => void;
  onClose: () => void;
  error: string | null;
}) {
  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex flex-col"
      style={{
        paddingTop: "env(safe-area-inset-top)",
        paddingBottom: "env(safe-area-inset-bottom)",
      }}
    >
      <div className="flex-1 flex flex-col p-3 gap-3 overflow-hidden">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">Edit variant</div>
          <button onClick={onClose} className="text-white/60 text-lg">
            ✕
          </button>
        </div>
        <p className="text-xs text-white/60">
          Edit the JSON below. Required fields: name, family, deck, deal,
          wilds, hand, hi_lo. The companion treats the variant as a custom
          one — pre-flop / draw / community streets all honored.
        </p>
        <textarea
          value={json}
          onChange={(e) => onJsonChange(e.target.value)}
          spellCheck={false}
          className="flex-1 rounded-lg bg-felt-dark text-white p-2 font-mono text-xs"
        />
        {error && <div className="text-red-300 text-sm">{error}</div>}
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={onClose}
            className="min-h-touch rounded-xl border border-white/20"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            className="min-h-touch rounded-xl bg-white text-felt-dark font-semibold"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function SlotBlock({
  label,
  cards,
  onRemove,
  onToggleWild,
  wildIndices,
  wildMode,
  isActive,
}: {
  label: string;
  cards: string[];
  onRemove: (i: number) => void;
  onToggleWild?: (i: number) => void;
  wildIndices?: number[];
  wildMode?: boolean;
  isActive: boolean;
}) {
  return (
    <div
      className={`rounded-xl p-3 ${
        isActive ? "bg-white/10 ring-2 ring-white/40" : "bg-felt-dark/40"
      }`}
    >
      <div className="text-xs uppercase tracking-wide text-white/60 mb-2">
        {label} ({cards.length})
      </div>
      <CardChips
        cards={cards}
        onRemove={onRemove}
        onToggleWild={wildMode ? onToggleWild : undefined}
        wildIndices={wildIndices}
        emptyLabel={wildMode ? "tap an existing chip to mark wild" : "tap a rank below to add a card"}
      />
    </div>
  );
}

function AnalysisView({ a }: { a: CompanionAnalysisView }) {
  return (
    <div className="rounded-xl bg-felt-dark/80 p-3 space-y-3 ring-1 ring-white/10">
      {a.hi && (
        <div>
          <div className="text-xs uppercase tracking-wide text-white/60">High</div>
          <div className="text-2xl font-semibold">{a.hi.cls_name}</div>
          <div className="text-sm text-white/70">{a.hi.explanation}</div>
          <div className="text-xs font-mono text-white/50 mt-1">
            {a.hi.cards.join(" ")}
          </div>
        </div>
      )}

      {a.lo && (
        <div>
          <div className="text-xs uppercase tracking-wide text-white/60">Low</div>
          <div className="text-2xl font-semibold">
            {a.lo.qualifies ? a.lo.name : "No qualifying low"}
          </div>
          <div className="text-sm text-white/70">{a.lo.explanation}</div>
          {a.lo.qualifies && (
            <div className="text-xs font-mono text-white/50 mt-1">
              {a.lo.cards.join(" ")}
            </div>
          )}
        </div>
      )}

      <div>
        <div className="text-xs uppercase tracking-wide text-white/60">Pot</div>
        <div className="text-sm">{a.hi_lo_explanation}</div>
      </div>

      {a.wild_resolution && (
        <div>
          <div className="text-xs uppercase tracking-wide text-white/60">Wilds</div>
          <div className="text-sm text-amber-100/90">{a.wild_resolution}</div>
        </div>
      )}

      {a.hands_that_beat_you.length > 0 && a.hi && (
        <div>
          <div className="text-xs uppercase tracking-wide text-white/60">
            Hands that beat you
          </div>
          <div className="text-xs text-white/60">
            {a.hands_that_beat_you.join(" · ")}
          </div>
        </div>
      )}
    </div>
  );
}

function EquityPanel({
  opponents,
  setOpponents,
  equity,
  busy,
  error,
  onRun,
  variant,
}: {
  opponents: number;
  setOpponents: (n: number) => void;
  equity: EquityResult | null;
  busy: boolean;
  error: string | null;
  onRun: () => void;
  variant: VariantWithMeta | null;
}) {
  const supported =
    !!variant
    && variant.deal.up_cards === 0
    && variant.deal.stud_streets.length === 0
    && variant.deal.draws.length === 0
    && variant.wilds.length === 0;
  return (
    <div className="rounded-xl bg-felt-dark/60 p-3 ring-1 ring-white/10 space-y-2">
      <div className="text-xs uppercase tracking-wide text-white/60">Equity (sim)</div>
      {!supported ? (
        <div className="text-xs text-white/50">
          Equity sim supports community-card variants without wilds. Use the
          companion above for variants with wild rules.
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <span className="text-xs text-white/60">vs</span>
            <button
              onClick={() => setOpponents(Math.max(1, opponents - 1))}
              className="min-w-touch min-h-touch rounded-lg border border-white/20"
            >
              −
            </button>
            <div className="flex-1 text-center font-mono">{opponents} opp</div>
            <button
              onClick={() => setOpponents(Math.min(8, opponents + 1))}
              className="min-w-touch min-h-touch rounded-lg border border-white/20"
            >
              +
            </button>
            <button
              onClick={onRun}
              disabled={busy}
              className="min-h-touch px-4 rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
            >
              {busy ? "…" : "Run"}
            </button>
          </div>
          {error && <div className="text-red-300 text-sm">{error}</div>}
          {equity && (
            <div className="grid grid-cols-3 gap-2 text-center text-sm">
              <Tile label="Win" value={`${equity.win_pct}%`} accent="emerald" />
              <Tile label="Tie" value={`${equity.tie_pct}%`} />
              <Tile label="Loss" value={`${equity.loss_pct}%`} accent="red" />
            </div>
          )}
          {equity && (
            <div className="text-xs text-white/50 text-center">
              {equity.iterations} sims · equity {equity.equity_pct}%
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "emerald" | "red";
}) {
  const color =
    accent === "emerald" ? "text-emerald-300"
    : accent === "red" ? "text-red-300"
    : "text-white";
  return (
    <div className="rounded-lg bg-white/5 p-2">
      <div className="text-[10px] uppercase tracking-wide text-white/50">{label}</div>
      <div className={`font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}
