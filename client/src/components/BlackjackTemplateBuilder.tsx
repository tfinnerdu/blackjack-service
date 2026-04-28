// Form-based blackjack template editor. Replaces the raw JSON sheet
// with structured controls for every Rules dimension. Power users
// can flip to the JSON view via the toggle in the header — same
// pattern as poker's VariantBuilder.

import { useEffect, useState } from "react";

export interface BlackjackTemplateDraft {
  name: string;
  description: string;
  rules: Record<string, any>;
  side_bets: Record<string, any>;
}

const SHUFFLE_MODES = [
  { value: "casino", label: "Casino (cut card)" },
  { value: "csm", label: "Continuous shuffler" },
  { value: "hand", label: "Hand-shuffled (imperfect)" },
];

const DOUBLE_RULES = [
  { value: "any2", label: "Any two cards" },
  { value: "9_10_11", label: "9 / 10 / 11 only" },
  { value: "10_11", label: "10 / 11 only" },
];

const SURRENDER_RULES = [
  { value: "none", label: "None" },
  { value: "late", label: "Late (after dealer peek)" },
  { value: "early", label: "Early (before dealer peek)" },
];

const PAYOUT_PRESETS: { label: string; value: [number, number] }[] = [
  { label: "3 : 2", value: [3, 2] },
  { label: "6 : 5", value: [6, 5] },
  { label: "1 : 1", value: [1, 1] },
  { label: "2 : 1", value: [2, 1] },
];

// Side bets the engine knows about. Flagging on/off via `enabled`. Per-tier
// payouts stay in JSON because they're paytable-specific and not what most
// users need to tweak.
const SIDE_BET_KEYS: { key: string; label: string }[] = [
  { key: "twenty_one_plus_three", label: "21 + 3" },
  { key: "perfect_pairs", label: "Perfect Pairs" },
  { key: "lucky_ladies", label: "Lucky Ladies" },
  { key: "royal_match", label: "Royal Match" },
  { key: "match_the_dealer", label: "Match the Dealer" },
  { key: "over_under_13", label: "Over / Under 13" },
  { key: "bust_it", label: "Bust It" },
  { key: "buster_blackjack", label: "Buster Blackjack" },
];

const BLANK_DRAFT: BlackjackTemplateDraft = {
  name: "My Custom Blackjack Rules",
  description: "",
  rules: {
    decks: 6,
    shuffle_mode: "casino",
    penetration: 0.75,
    seats: 5,
    player_seat: 3,
    dealer_hits_soft_17: true,
    dealer_peeks: true,
    european_no_hole_card: false,
    blackjack_payout: [3, 2],
    insurance_payout: [2, 1],
    double_rule: "any2",
    double_after_split: true,
    max_splits: 3,
    resplit_aces: false,
    hit_split_aces: false,
    surrender: "late",
    insurance_offered: true,
    starting_bankroll: 500,
    min_bet: 5,
    max_bet: 500,
    bet_increment: 5,
  },
  side_bets: {},
};

export function buildBlankBlackjackDraft(): BlackjackTemplateDraft {
  return JSON.parse(JSON.stringify(BLANK_DRAFT));
}

export function BlackjackTemplateBuilder({
  initial,
  onSave,
  onCancel,
  error,
}: {
  initial: BlackjackTemplateDraft;
  onSave: (d: BlackjackTemplateDraft) => void;
  onCancel: () => void;
  error: string | null;
}) {
  const [d, setD] = useState<BlackjackTemplateDraft>(initial);
  const [showJson, setShowJson] = useState(false);
  const [jsonText, setJsonText] = useState(() => JSON.stringify(initial, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  useEffect(() => {
    setJsonText(JSON.stringify(d, null, 2));
  }, [d]);

  function setField(path: string, value: any) {
    setD((cur) => {
      const copy = JSON.parse(JSON.stringify(cur));
      const segments = path.split(".");
      let cursor: any = copy;
      for (let i = 0; i < segments.length - 1; i++) {
        cursor = cursor[segments[i]] ??= {};
      }
      cursor[segments[segments.length - 1]] = value;
      return copy;
    });
  }

  function setRule(key: string, value: any) {
    setField(`rules.${key}`, value);
  }

  function setSideBetEnabled(key: string, enabled: boolean) {
    setD((cur) => {
      const next = JSON.parse(JSON.stringify(cur));
      const existing = next.side_bets[key] ?? {};
      next.side_bets[key] = { ...existing, enabled };
      return next;
    });
  }

  function commitJsonView() {
    try {
      const parsed = JSON.parse(jsonText);
      setD(parsed);
      setJsonError(null);
      setShowJson(false);
    } catch {
      setJsonError("invalid JSON");
    }
  }

  function save() {
    if (showJson) {
      try {
        onSave(JSON.parse(jsonText));
      } catch {
        setJsonError("invalid JSON");
      }
      return;
    }
    if (!d.name.trim()) {
      setJsonError("name required");
      return;
    }
    onSave(d);
  }

  const r = d.rules;

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
          <div className="text-lg font-semibold">Blackjack template builder</div>
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
                  value={d.name}
                  onChange={(e) => setField("name", e.target.value)}
                />
              </Field>
              <Field label="Description">
                <input
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={d.description}
                  onChange={(e) => setField("description", e.target.value)}
                />
              </Field>
            </Section>

            <Section title="Shoe">
              <Field label="Decks">
                <Stepper value={r.decks} setValue={(n) => setRule("decks", n)} min={1} max={8} />
              </Field>
              <Field label="Shuffle mode">
                <select
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={r.shuffle_mode}
                  onChange={(e) => setRule("shuffle_mode", e.target.value)}
                >
                  {SHUFFLE_MODES.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Penetration">
                <PercentStepper
                  value={r.penetration}
                  setValue={(n) => setRule("penetration", n)}
                  min={0.3}
                  max={1.0}
                  step={0.05}
                />
              </Field>
            </Section>

            <Section title="Dealer">
              <Toggle
                label="Hits soft 17 (H17)"
                checked={!!r.dealer_hits_soft_17}
                onChange={(b) => setRule("dealer_hits_soft_17", b)}
              />
              <Toggle
                label="Peeks for blackjack on A / 10"
                checked={!!r.dealer_peeks}
                onChange={(b) => setRule("dealer_peeks", b)}
              />
              <Toggle
                label="European no-hole-card (ENHC)"
                checked={!!r.european_no_hole_card}
                onChange={(b) => setRule("european_no_hole_card", b)}
              />
            </Section>

            <Section title="Payouts">
              <Field label="Blackjack pays">
                <PayoutPicker
                  value={r.blackjack_payout}
                  onChange={(v) => setRule("blackjack_payout", v)}
                />
              </Field>
              <Field label="Insurance pays">
                <PayoutPicker
                  value={r.insurance_payout}
                  onChange={(v) => setRule("insurance_payout", v)}
                />
              </Field>
            </Section>

            <Section title="Double / split / surrender">
              <Field label="Doubling allowed on">
                <select
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={r.double_rule}
                  onChange={(e) => setRule("double_rule", e.target.value)}
                >
                  {DOUBLE_RULES.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </Field>
              <Toggle
                label="Double after split"
                checked={!!r.double_after_split}
                onChange={(b) => setRule("double_after_split", b)}
              />
              <Field label="Max additional splits">
                <Stepper
                  value={r.max_splits ?? 3}
                  setValue={(n) => setRule("max_splits", n)}
                  min={0}
                  max={4}
                />
              </Field>
              <Toggle
                label="Re-split aces"
                checked={!!r.resplit_aces}
                onChange={(b) => setRule("resplit_aces", b)}
              />
              <Toggle
                label="Hit split aces"
                checked={!!r.hit_split_aces}
                onChange={(b) => setRule("hit_split_aces", b)}
              />
              <Field label="Surrender">
                <select
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                  value={r.surrender}
                  onChange={(e) => setRule("surrender", e.target.value)}
                >
                  {SURRENDER_RULES.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </Field>
              <Toggle
                label="Offer insurance"
                checked={!!r.insurance_offered}
                onChange={(b) => setRule("insurance_offered", b)}
              />
            </Section>

            <Section title="Money">
              <Field label="Starting bankroll">
                <Stepper
                  value={r.starting_bankroll ?? 500}
                  setValue={(n) => setRule("starting_bankroll", n)}
                  step={50}
                  min={50}
                />
              </Field>
              <Field label="Min bet">
                <Stepper
                  value={r.min_bet ?? 5}
                  setValue={(n) => setRule("min_bet", n)}
                  step={1}
                  min={1}
                />
              </Field>
              <Field label="Max bet">
                <Stepper
                  value={r.max_bet ?? 500}
                  setValue={(n) => setRule("max_bet", n)}
                  step={25}
                  min={5}
                />
              </Field>
              <Field label="Bet increment">
                <Stepper
                  value={r.bet_increment ?? 5}
                  setValue={(n) => setRule("bet_increment", n)}
                  step={1}
                  min={1}
                />
              </Field>
            </Section>

            <Section title="Side bets (offered)">
              <p className="text-xs text-white/50 mb-2">
                Toggle which side bets the table offers. Tweak the per-tier
                payouts via the JSON view if you want non-standard paytables.
              </p>
              <div className="space-y-1">
                {SIDE_BET_KEYS.map((sb) => (
                  <Toggle
                    key={sb.key}
                    label={sb.label}
                    checked={!!d.side_bets?.[sb.key]?.enabled}
                    onChange={(b) => setSideBetEnabled(sb.key, b)}
                  />
                ))}
              </div>
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
      <div className="text-xs text-white/70 flex-1">{label}</div>
      <div className="flex-1">{children}</div>
    </label>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (b: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3 min-h-touch">
      <div className="text-sm flex-1">{label}</div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-5 h-5"
      />
    </label>
  );
}

function Stepper({
  value,
  setValue,
  min,
  max,
  step = 1,
}: {
  value: number;
  setValue: (n: number) => void;
  min: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => setValue(Math.max(min, value - step))}
        className="min-w-[40px] min-h-touch rounded-lg border border-white/20"
      >
        −
      </button>
      <div className="flex-1 text-center font-mono">{value}</div>
      <button
        onClick={() => setValue(max !== undefined ? Math.min(max, value + step) : value + step)}
        className="min-w-[40px] min-h-touch rounded-lg border border-white/20"
      >
        +
      </button>
    </div>
  );
}

function PercentStepper({
  value,
  setValue,
  min,
  max,
  step,
}: {
  value: number;
  setValue: (n: number) => void;
  min: number;
  max: number;
  step: number;
}) {
  function fmt(n: number) {
    return `${Math.round(n * 100)}%`;
  }
  function clamp(n: number) {
    return Math.max(min, Math.min(max, Number(n.toFixed(2))));
  }
  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => setValue(clamp(value - step))}
        className="min-w-[40px] min-h-touch rounded-lg border border-white/20"
      >
        −
      </button>
      <div className="flex-1 text-center font-mono">{fmt(value)}</div>
      <button
        onClick={() => setValue(clamp(value + step))}
        className="min-w-[40px] min-h-touch rounded-lg border border-white/20"
      >
        +
      </button>
    </div>
  );
}

function PayoutPicker({
  value,
  onChange,
}: {
  value: [number, number] | number[];
  onChange: (v: [number, number]) => void;
}) {
  const current = Array.isArray(value) ? `${value[0]}:${value[1]}` : "";
  return (
    <select
      className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
      value={current}
      onChange={(e) => {
        const found = PAYOUT_PRESETS.find((p) => `${p.value[0]}:${p.value[1]}` === e.target.value);
        if (found) onChange(found.value);
      }}
    >
      {PAYOUT_PRESETS.map((p) => (
        <option key={`${p.value[0]}:${p.value[1]}`} value={`${p.value[0]}:${p.value[1]}`}>
          {p.label}
        </option>
      ))}
    </select>
  );
}
