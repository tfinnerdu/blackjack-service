// Form-based variant editor. Replaces the raw JSON textarea with
// structured fields for every dimension of the variant DSL. The wilds
// section is the headline change — inline list with kind/mode pickers
// rather than 'edit JSON and hope you got the brackets right'.
//
// Power users can flip to the JSON editor via the toggle in the header.

import { useEffect, useState } from "react";

import { VariantSpec } from "../../lib/poker";

interface DraftWildRule {
  kind: string;
  mode: string;
  rank?: string;
  suit?: string;
  card_token?: string;
}

const WILD_KINDS = [
  { value: "joker", label: "Joker" },
  { value: "rank", label: "All cards of rank" },
  { value: "suit", label: "All cards of suit" },
  { value: "specific", label: "Specific card" },
  { value: "one_eyed_jack", label: "One-eyed jacks" },
  { value: "suicide_king", label: "Suicide king" },
];

const WILD_MODES = [
  { value: "fully_wild", label: "Fully wild" },
  { value: "straight_flush_only", label: "S/F only (dies otherwise)" },
  { value: "bug", label: "Bug (S/F or plays as ace)" },
];

const RANK_OPTIONS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K"];
const SUIT_OPTIONS = ["S", "H", "D", "C"];

const HAND_OPTIONS = [
  { value: "best_5_of_all", label: "Best 5 of all visible cards" },
  { value: "omaha_2_hole_3_board", label: "Must use 2 hole + 3 board (Omaha)" },
  { value: "exactly_5_hole", label: "Exactly 5 hole cards (draw)" },
  { value: "badugi_4_of_hole", label: "4 cards (badugi)" },
  { value: "exactly_4_hole", label: "Exactly 4 hole cards" },
];

const HILO_OPTIONS = [
  { value: "hi_only", label: "High only" },
  { value: "lo_only", label: "Low only" },
  { value: "split", label: "Split high/low" },
];

const LO_RULES = [
  { value: "", label: "—" },
  { value: "ace_to_five", label: "Ace-to-five (A=1, no S/F penalty)" },
  { value: "deuce_to_seven", label: "Deuce-to-seven (A high, S/F count)" },
  { value: "badugi", label: "Badugi (4 distinct ranks + suits)" },
];

const FAMILY_OPTIONS = ["holdem", "omaha", "stud", "draw", "badugi", "home"];

export function VariantBuilder({
  initial,
  onSave,
  onCancel,
  error,
}: {
  initial: VariantSpec;
  onSave: (v: VariantSpec) => void;
  onCancel: () => void;
  error: string | null;
}) {
  const [v, setV] = useState<VariantSpec>(initial);
  const [showJson, setShowJson] = useState(false);
  const [jsonText, setJsonText] = useState(() => JSON.stringify(initial, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Keep JSON view in sync when the form mutates it.
  useEffect(() => {
    setJsonText(JSON.stringify(v, null, 2));
  }, [v]);

  function update<K extends keyof VariantSpec>(key: K, value: VariantSpec[K]) {
    setV((cur) => ({ ...cur, [key]: value }));
  }

  function updateDeal(key: keyof VariantSpec["deal"], value: any) {
    setV((cur) => ({ ...cur, deal: { ...cur.deal, [key]: value } }));
  }

  function updateDeck(key: keyof VariantSpec["deck"], value: number) {
    setV((cur) => ({ ...cur, deck: { ...cur.deck, [key]: value } }));
  }

  function setWilds(wilds: DraftWildRule[]) {
    setV((cur) => ({ ...cur, wilds: wilds as any }));
  }

  function addWild() {
    setWilds([...((v.wilds as DraftWildRule[]) ?? []), { kind: "rank", mode: "fully_wild", rank: "Q" }]);
  }

  function updateWild(i: number, partial: Partial<DraftWildRule>) {
    const next = [...((v.wilds as DraftWildRule[]) ?? [])];
    next[i] = { ...next[i], ...partial };
    setWilds(next);
  }

  function removeWild(i: number) {
    const next = [...((v.wilds as DraftWildRule[]) ?? [])];
    next.splice(i, 1);
    setWilds(next);
  }

  function commitJsonView() {
    try {
      const parsed = JSON.parse(jsonText);
      setV(parsed);
      setJsonError(null);
      setShowJson(false);
    } catch {
      setJsonError("invalid JSON");
    }
  }

  function save() {
    if (showJson) {
      try {
        const parsed = JSON.parse(jsonText);
        onSave(parsed);
      } catch {
        setJsonError("invalid JSON");
      }
    } else {
      onSave(v);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex flex-col"
      style={{
        paddingTop: "env(safe-area-inset-top)",
        paddingBottom: "env(safe-area-inset-bottom)",
      }}
    >
      <div className="flex-1 flex flex-col p-3 gap-3 overflow-y-auto">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">Variant builder</div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => (showJson ? commitJsonView() : setShowJson(true))}
              className="text-xs text-white/60 underline"
            >
              {showJson ? "Use form" : "Show JSON"}
            </button>
            <button onClick={onCancel} className="text-white/60 text-lg">✕</button>
          </div>
        </div>

        {showJson ? (
          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            spellCheck={false}
            className="flex-1 min-h-[40vh] rounded-lg bg-felt-dark text-white p-2 font-mono text-xs"
          />
        ) : (
          <div className="space-y-4">
            <Section title="Identity">
              <Field label="Name">
                <input
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={v.name}
                  onChange={(e) => update("name", e.target.value)}
                />
              </Field>
              <Field label="Description">
                <input
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={v.description}
                  onChange={(e) => update("description", e.target.value)}
                />
              </Field>
              <Field label="Family">
                <select
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={v.family}
                  onChange={(e) => update("family", e.target.value)}
                >
                  {FAMILY_OPTIONS.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </Field>
            </Section>

            <Section title="Deck">
              <Field label="Decks">
                <Stepper value={v.deck.decks} setValue={(n) => updateDeck("decks", n)} min={1} max={4} />
              </Field>
              <Field label="Jokers">
                <Stepper value={v.deck.jokers} setValue={(n) => updateDeck("jokers", n)} min={0} max={2} />
              </Field>
            </Section>

            <Section title="Deal">
              <Field label="Hole cards (face-down)">
                <Stepper value={v.deal.hole_cards} setValue={(n) => updateDeal("hole_cards", n)} min={0} max={10} />
              </Field>
              <Field label="Up cards (face-up, stud)">
                <Stepper value={v.deal.up_cards} setValue={(n) => updateDeal("up_cards", n)} min={0} max={6} />
              </Field>
              <Field label="Community streets (e.g. 3,1,1)">
                <input
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white font-mono"
                  value={v.deal.community_streets.join(",")}
                  onChange={(e) =>
                    updateDeal("community_streets",
                      e.target.value.split(",").map((s) => parseInt(s.trim(), 10)).filter(Number.isFinite))
                  }
                  placeholder="empty for non-community games"
                />
              </Field>
              <Field label="Stud streets (e.g. 1,1,1,1)">
                <input
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white font-mono"
                  value={v.deal.stud_streets.join(",")}
                  onChange={(e) =>
                    updateDeal("stud_streets",
                      e.target.value.split(",").map((s) => parseInt(s.trim(), 10)).filter(Number.isFinite))
                  }
                />
              </Field>
              <Field label="Last stud card face-down">
                <input
                  type="checkbox"
                  checked={v.deal.stud_face_down_final}
                  onChange={(e) => updateDeal("stud_face_down_final", e.target.checked)}
                />
              </Field>
              <Field label="Draws (per-round max replace, e.g. 5,5,5)">
                <input
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white font-mono"
                  value={v.deal.draws.join(",")}
                  onChange={(e) =>
                    updateDeal("draws",
                      e.target.value.split(",").map((s) => parseInt(s.trim(), 10)).filter(Number.isFinite))
                  }
                />
              </Field>
            </Section>

            <Section title="Wild rules">
              <div className="space-y-2">
                {((v.wilds as DraftWildRule[]) ?? []).map((w, i) => (
                  <div key={i} className="rounded-lg bg-felt-dark/60 p-2 space-y-2">
                    <div className="flex gap-2">
                      <select
                        className="flex-1 min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                        value={w.kind}
                        onChange={(e) => updateWild(i, { kind: e.target.value })}
                      >
                        {WILD_KINDS.map((k) => (
                          <option key={k.value} value={k.value}>{k.label}</option>
                        ))}
                      </select>
                      <button
                        onClick={() => removeWild(i)}
                        className="min-h-touch min-w-touch rounded-lg border border-white/20"
                      >
                        ×
                      </button>
                    </div>
                    <select
                      className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                      value={w.mode}
                      onChange={(e) => updateWild(i, { mode: e.target.value })}
                    >
                      {WILD_MODES.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                    {w.kind === "rank" && (
                      <select
                        className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                        value={w.rank ?? ""}
                        onChange={(e) => updateWild(i, { rank: e.target.value })}
                      >
                        <option value="">— pick rank —</option>
                        {RANK_OPTIONS.map((r) => (
                          <option key={r} value={r}>{r === "T" ? "10" : r}</option>
                        ))}
                      </select>
                    )}
                    {w.kind === "suit" && (
                      <select
                        className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                        value={w.suit ?? ""}
                        onChange={(e) => updateWild(i, { suit: e.target.value })}
                      >
                        <option value="">— pick suit —</option>
                        {SUIT_OPTIONS.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    )}
                    {w.kind === "specific" && (
                      <input
                        className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white font-mono"
                        value={w.card_token ?? ""}
                        onChange={(e) => updateWild(i, { card_token: e.target.value.toUpperCase() })}
                        placeholder="e.g. JS"
                      />
                    )}
                  </div>
                ))}
                <button
                  onClick={addWild}
                  className="w-full min-h-touch rounded-lg border border-white/20"
                >
                  + Add wild rule
                </button>
              </div>
            </Section>

            <Section title="Hand + Hi/Lo">
              <Field label="Hand requirement">
                <select
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={v.hand}
                  onChange={(e) => update("hand", e.target.value as any)}
                >
                  {HAND_OPTIONS.map((h) => (
                    <option key={h.value} value={h.value}>{h.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Hi / Lo split">
                <select
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={v.hi_lo}
                  onChange={(e) => update("hi_lo", e.target.value as any)}
                >
                  {HILO_OPTIONS.map((h) => (
                    <option key={h.value} value={h.value}>{h.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Low rule">
                <select
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={v.lo_rule ?? ""}
                  onChange={(e) => update("lo_rule", (e.target.value || null) as any)}
                >
                  {LO_RULES.map((l) => (
                    <option key={l.value} value={l.value}>{l.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="8-or-better qualifier">
                <input
                  type="checkbox"
                  checked={v.lo_eight_or_better}
                  onChange={(e) => update("lo_eight_or_better", e.target.checked as any)}
                />
              </Field>
            </Section>

            <Section title="Notes">
              <textarea
                rows={3}
                className="w-full rounded-lg bg-felt-dark px-2 py-2 text-white text-sm"
                value={v.notes}
                onChange={(e) => update("notes", e.target.value)}
              />
            </Section>
          </div>
        )}

        {(error || jsonError) && (
          <div className="text-red-300 text-sm">{error ?? jsonError}</div>
        )}
        <div className="grid grid-cols-2 gap-2 sticky bottom-0 bg-felt-dark/90 backdrop-blur pt-2">
          <button
            onClick={onCancel}
            className="min-h-touch rounded-xl border border-white/20"
          >
            Cancel
          </button>
          <button
            onClick={save}
            className="min-h-touch rounded-xl bg-white text-felt-dark font-semibold"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-white/60 mb-2">{title}</div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-3">
      <div className="text-xs text-white/60 flex-1">{label}</div>
      <div className="flex-1">{children}</div>
    </label>
  );
}

function Stepper({
  value,
  setValue,
  min,
  max,
}: {
  value: number;
  setValue: (n: number) => void;
  min: number;
  max: number;
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => setValue(Math.max(min, value - 1))}
        className="min-w-touch min-h-touch rounded-lg border border-white/20"
      >
        −
      </button>
      <div className="flex-1 text-center font-mono">{value}</div>
      <button
        onClick={() => setValue(Math.min(max, value + 1))}
        className="min-w-touch min-h-touch rounded-lg border border-white/20"
      >
        +
      </button>
    </div>
  );
}
