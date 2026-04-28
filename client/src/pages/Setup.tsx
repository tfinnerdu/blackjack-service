import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  BlackjackTemplateBuilder,
  BlackjackTemplateDraft,
  buildBlankBlackjackDraft,
} from "../components/BlackjackTemplateBuilder";
import { ApiError, Sessions, Templates } from "../lib/api";
import { useApp } from "../lib/store";
import type { TemplateView } from "../lib/types";

const PLAYSTYLES = [
  "book", "counter", "tight", "aggressive", "mimic_dealer",
  "hunch", "drunk", "superstitious", "streaky",
] as const;
const BET_PATTERNS = [
  "flat", "martingale", "anti_martingale", "oscars_grind",
  "count_spread", "random", "streaky",
] as const;

export default function Setup() {
  const setSession = useApp((s) => s.setSession);
  const navigate = useNavigate();

  const [templates, setTemplates] = useState<TemplateView[]>([]);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [bankroll, setBankroll] = useState(500);
  const [seats, setSeats] = useState(5);
  const [playerSeat, setPlayerSeat] = useState(3);
  const [aiByseat, setAiBySeat] = useState<Record<number, { playstyle: string; bet_pattern: string; base_bet: number }>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorDraft, setEditorDraft] = useState<BlackjackTemplateDraft | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);

  useEffect(() => {
    Templates.list("blackjack")
      .then((d) => {
        setTemplates(d.templates);
        const builtin = d.templates.find((t) => t.is_builtin);
        if (builtin) setTemplateId(builtin.id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === templateId) || null,
    [templates, templateId],
  );

  // When a template is picked, default the seats / player seat / bankroll
  // off it so the controls below match the template's intent.
  useEffect(() => {
    if (!selectedTemplate) return;
    const r = selectedTemplate.rules;
    if (typeof r.seats === "number") setSeats(r.seats);
    if (typeof r.player_seat === "number") setPlayerSeat(r.player_seat);
    if (typeof r.starting_bankroll === "number") setBankroll(r.starting_bankroll);
  }, [selectedTemplate]);

  // Ensure player seat is within seats and AI map covers the rest.
  useEffect(() => {
    if (playerSeat < 1) setPlayerSeat(1);
    if (playerSeat > seats) setPlayerSeat(seats);
    setAiBySeat((current) => {
      const next: typeof current = {};
      for (let i = 1; i <= seats; i++) {
        if (i === playerSeat) continue;
        next[i] = current[i] ?? { playstyle: "book", bet_pattern: "flat", base_bet: 10 };
      }
      return next;
    });
  }, [seats, playerSeat]);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const ai_seats = Object.entries(aiByseat).map(([k, v]) => ({
        seat_num: Number(k),
        playstyle: v.playstyle,
        bet_pattern: v.bet_pattern,
        base_bet: v.base_bet,
        bankroll: bankroll,
        rebuy_on_bust: false,
      }));
      const sess = await Sessions.create({
        template_id: templateId,
        starting_bankroll: bankroll,
        player_seat: playerSeat,
        ai_seats,
        rules: { seats, player_seat: playerSeat },
      });
      setSession(sess);
      navigate("/play");
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.code}: ${e.message}` : String(e);
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  function refreshTemplates() {
    return Templates.list("blackjack")
      .then((d) => setTemplates(d.templates))
      .catch((e) => setError(String(e)));
  }

  function openEditorBlank() {
    setEditorDraft(buildBlankBlackjackDraft());
    setEditorError(null);
    setEditorOpen(true);
  }

  function openEditorClone() {
    if (!selectedTemplate) return;
    setEditorDraft({
      name: `${selectedTemplate.name} (copy)`,
      description: selectedTemplate.description,
      rules: { ...selectedTemplate.rules },
      side_bets: { ...selectedTemplate.side_bets },
    });
    setEditorError(null);
    setEditorOpen(true);
  }

  async function saveTemplate(draft: BlackjackTemplateDraft) {
    if (!draft.name?.trim()) {
      setEditorError("name required");
      return;
    }
    try {
      const saved = await Templates.create({
        game_type: "blackjack",
        name: draft.name,
        description: draft.description ?? "",
        rules: draft.rules ?? {},
        side_bets: draft.side_bets ?? {},
      });
      await refreshTemplates();
      setTemplateId(saved.id);
      setEditorOpen(false);
      setEditorDraft(null);
    } catch (e) {
      setEditorError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  }

  async function deleteSelectedTemplate() {
    if (!selectedTemplate || selectedTemplate.is_builtin) return;
    if (!confirm(`Delete "${selectedTemplate.name}"?`)) return;
    try {
      await Templates.destroy(selectedTemplate.id);
      await refreshTemplates();
      // Pick the first remaining built-in.
      const builtin = templates.find(
        (t) => t.is_builtin && t.id !== selectedTemplate.id,
      );
      setTemplateId(builtin?.id ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  }

  return (
    <div
      className="min-h-screen px-4 py-6"
      style={{ paddingTop: "calc(env(safe-area-inset-top) + 16px)", paddingBottom: "calc(env(safe-area-inset-bottom) + 96px)" }}
    >
      <div className="max-w-md mx-auto space-y-6">
        <h1 className="text-2xl font-bold">New session</h1>

        <Section title="Rules template">
          <select
            className="w-full min-h-touch rounded-xl bg-felt text-white px-3"
            value={templateId ?? ""}
            onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Custom (defaults)</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          {selectedTemplate && (
            <p className="text-xs text-white/60 mt-2">{selectedTemplate.description}</p>
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
              disabled={!selectedTemplate}
              className="min-h-touch rounded-lg border border-white/20 text-xs disabled:opacity-40"
            >
              Clone
            </button>
            <button
              onClick={deleteSelectedTemplate}
              disabled={!selectedTemplate || selectedTemplate.is_builtin}
              className="min-h-touch rounded-lg border border-red-300/40 text-red-200 text-xs disabled:opacity-30"
            >
              Delete
            </button>
          </div>
        </Section>

        <Section title="Bankroll">
          <NumberStepper value={bankroll} setValue={setBankroll} step={50} min={50} />
        </Section>

        <Section title="Table size">
          <NumberStepper value={seats} setValue={setSeats} step={1} min={1} max={7} />
        </Section>

        <Section title="Your seat">
          <div className="grid grid-cols-7 gap-2">
            {Array.from({ length: seats }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                onClick={() => setPlayerSeat(n)}
                className={`min-h-touch rounded-xl border ${
                  playerSeat === n
                    ? "bg-white text-felt-dark border-white"
                    : "border-white/20 text-white"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </Section>

        {seats > 1 && (
          <Section title="Other players">
            <div className="space-y-3">
              {Object.entries(aiByseat).map(([k, v]) => (
                <div key={k} className="rounded-xl bg-felt p-3 space-y-2">
                  <div className="text-sm text-white/70">Seat {k}</div>
                  <select
                    className="w-full min-h-touch rounded-lg bg-felt-dark text-white px-2"
                    value={v.playstyle}
                    onChange={(e) =>
                      setAiBySeat({ ...aiByseat, [Number(k)]: { ...v, playstyle: e.target.value } })
                    }
                  >
                    {PLAYSTYLES.map((p) => (
                      <option key={p} value={p}>
                        {p.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                  <select
                    className="w-full min-h-touch rounded-lg bg-felt-dark text-white px-2"
                    value={v.bet_pattern}
                    onChange={(e) =>
                      setAiBySeat({ ...aiByseat, [Number(k)]: { ...v, bet_pattern: e.target.value } })
                    }
                  >
                    {BET_PATTERNS.map((p) => (
                      <option key={p} value={p}>
                        {p.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                  <NumberStepper
                    value={v.base_bet}
                    setValue={(x) =>
                      setAiBySeat({ ...aiByseat, [Number(k)]: { ...v, base_bet: x } })
                    }
                    step={5}
                    min={1}
                    label="base bet"
                  />
                </div>
              ))}
            </div>
          </Section>
        )}

        {error && <div className="text-red-300 text-sm">{error}</div>}
      </div>

      <div
        className="fixed bottom-0 inset-x-0 px-4 pt-3 pb-safe-bot bg-felt-dark/90 backdrop-blur"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
      >
        <button
          onClick={submit}
          disabled={submitting}
          className="w-full max-w-md mx-auto block min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          {submitting ? "Starting…" : "Deal me in"}
        </button>
      </div>

      {editorOpen && editorDraft && (
        <BlackjackTemplateBuilder
          initial={editorDraft}
          onSave={saveTemplate}
          onCancel={() => {
            setEditorOpen(false);
            setEditorDraft(null);
          }}
          error={editorError}
        />
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-xs uppercase tracking-wider text-white/60 mb-2">{title}</h2>
      {children}
    </div>
  );
}

function NumberStepper({
  value,
  setValue,
  step,
  min,
  max,
  label,
}: {
  value: number;
  setValue: (n: number) => void;
  step: number;
  min: number;
  max?: number;
  label?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setValue(Math.max(min, value - step))}
        className="min-w-touch min-h-touch rounded-xl border border-white/20 text-xl"
      >
        −
      </button>
      <div className="flex-1 text-center text-2xl font-mono">
        {value}
        {label && <span className="text-xs text-white/60 ml-2">{label}</span>}
      </div>
      <button
        onClick={() => setValue(max !== undefined ? Math.min(max, value + step) : value + step)}
        className="min-w-touch min-h-touch rounded-xl border border-white/20 text-xl"
      >
        +
      </button>
    </div>
  );
}
