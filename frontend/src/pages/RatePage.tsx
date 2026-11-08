import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { OnboardingCard } from "../api/types";
import Poster, { posterUrl } from "../components/Poster";
import TasteGroupPicker from "../components/TasteGroupPicker";
import { useSaveTastePreferences, useTastePreferences } from "../hooks/useLibrary";

const SCORES = [1, 2, 3, 4, 5] as const;
const SKELETON_CARDS = 12;
const ANSWERS_PATH = "/api/onboarding/answers";
const RECOMPUTE_PATH = "/api/jobs/recompute-taste";

type Ratings = Record<number, number>;
type Change = { id: number; previous: number | undefined };
type Page = { cards: OnboardingCard[]; ratings: Ratings };

function ratingList(ratings: Ratings) {
  return Object.entries(ratings).map(([id, score]) => ({ movie_id: Number(id), score }));
}

function Stars({
  title,
  value,
  onRate,
}: {
  title: string;
  value: number | undefined;
  onRate: (score: number) => void;
}) {
  return (
    <div className="mt-0.5 flex" role="group" aria-label={`${title} için puan`}>
      {SCORES.map((score) => (
        <button
          key={score}
          type="button"
          aria-label={`${score} yıldız`}
          aria-pressed={value === score}
          onClick={() => onRate(score)}
          className="flex h-11 flex-1 items-center justify-center rounded-md hover:bg-neutral-800"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill={(value ?? 0) >= score ? "var(--color-amber-400)" : "#4a4753"}
              d="M12 2.5l2.9 6.2 6.8.8-5 4.6 1.3 6.7L12 17.5l-6 3.3 1.3-6.7-5-4.6 6.8-.8z"
            />
          </svg>
        </button>
      ))}
    </div>
  );
}

export default function RatePage() {
  const qc = useQueryClient();
  const preferences = useTastePreferences();
  const savePreferences = useSaveTastePreferences();
  const [editingGroups, setEditingGroups] = useState(false);
  const ready = preferences.data?.completed === true && !editingGroups;

  const [cards, setCards] = useState<OnboardingCard[]>([]);
  const [ratings, setRatings] = useState<Ratings>({});
  const [changes, setChanges] = useState<Change[]>([]);
  const [previousPage, setPreviousPage] = useState<Page | null>(null);
  const [busy, setBusy] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loading = useRef(false);
  const hovered = useRef<number | null>(null);
  const ratingsRef = useRef(ratings);
  ratingsRef.current = ratings;
  const answeredThisSession = useRef(false);

  const refreshProgress = useCallback(
    () => void qc.invalidateQueries({ queryKey: ["progress"] }),
    [qc],
  );

  const loadPage = useCallback(async (previous: number | null) => {
    if (loading.current) return;
    loading.current = true;
    setBusy(true);
    try {
      const batch = await api.nextCards([], previous);
      setCards(batch.cards);
      setRatings({});
      setChanges([]);
      setExhausted(batch.cards.length === 0);
      setError(null);
      batch.cards.forEach((c) => {
        if (c.poster_path) new Image().src = posterUrl(c.poster_path);
      });
      window.scrollTo({ top: 0 });
    } catch {
      setError("Filmler alınamadı. Sunucu çalışıyor mu?");
    } finally {
      loading.current = false;
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (ready && cards.length === 0 && !exhausted) void loadPage(null);
  }, [ready, cards.length, exhausted, loadPage]);

  // Sayfadan çıkınca bitmemiş sayfadaki yıldızlar saklanır ve zevk yeniden hesaplanır.
  useEffect(() => {
    const flushBeacon = () => {
      const rated = ratingList(ratingsRef.current);
      if (rated.length > 0) {
        const body = JSON.stringify({ ratings: rated, skips: [] });
        navigator.sendBeacon(ANSWERS_PATH, new Blob([body], { type: "application/json" }));
        ratingsRef.current = {};
        answeredThisSession.current = true;
      }
      if (answeredThisSession.current) {
        navigator.sendBeacon(RECOMPUTE_PATH);
        answeredThisSession.current = false;
      }
    };
    window.addEventListener("pagehide", flushBeacon);
    return () => {
      window.removeEventListener("pagehide", flushBeacon);
      const rated = ratingList(ratingsRef.current);
      if (rated.length === 0 && !answeredThisSession.current) return;
      ratingsRef.current = {};
      answeredThisSession.current = false;
      void api
        .saveAnswers(rated, [])
        .then(() => api.submitRecompute())
        .catch(() => undefined);
    };
  }, []);

  const rate = useCallback((id: number, score: number) => {
    const current = ratingsRef.current;
    const previous = current[id];
    const next = { ...current };
    if (previous === score) delete next[id];
    else next[id] = score;
    ratingsRef.current = next;
    setRatings(next);
    setChanges((list) => [...list, { id, previous }]);
  }, []);

  const goNext = useCallback(async () => {
    if (loading.current || cards.length === 0) return;
    const rated = ratingList(ratings);
    const skips = cards.filter((c) => ratings[c.tmdb_id] === undefined).map((c) => c.tmdb_id);
    setBusy(true);
    try {
      await api.saveAnswers(rated, skips);
      answeredThisSession.current = true;
      ratingsRef.current = {};
      setPreviousPage({ cards, ratings });
      refreshProgress();
      await loadPage(cards.at(-1)?.tmdb_id ?? null);
    } catch {
      setBusy(false);
      setError("Kaydedilemedi. Sunucu çalışıyor mu?");
    }
  }, [cards, ratings, loadPage, refreshProgress]);

  const undo = useCallback(async () => {
    const last = changes.at(-1);
    if (last) {
      setRatings((current) => {
        const next = { ...current };
        if (last.previous === undefined) delete next[last.id];
        else next[last.id] = last.previous;
        return next;
      });
      setChanges((list) => list.slice(0, -1));
      return;
    }
    if (!previousPage) return;
    setBusy(true);
    try {
      await api.removeAnswers(previousPage.cards.map((c) => c.tmdb_id));
      setCards(previousPage.cards);
      setRatings(previousPage.ratings);
      setPreviousPage(null);
      setExhausted(false);
      refreshProgress();
    } catch {
      setError("Geri alınamadı. Sunucu çalışıyor mu?");
    } finally {
      setBusy(false);
    }
  }, [changes, previousPage, refreshProgress]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!ready || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key >= "1" && e.key <= "5" && hovered.current !== null) {
        rate(hovered.current, Number(e.key));
      } else if (e.key === "Enter" && !(e.target instanceof HTMLButtonElement)) {
        void goNext();
      } else if (e.key === "z" || e.key === "Z") {
        void undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ready, rate, goNext, undo]);

  const saveGroups = (groupIds: string[]) =>
    savePreferences.mutate(groupIds, {
      onSuccess: () => {
        setCards([]);
        setRatings({});
        setChanges([]);
        setPreviousPage(null);
        setExhausted(false);
        setEditingGroups(false);
      },
    });

  if (preferences.data && !ready) {
    return (
      <TasteGroupPicker
        groups={preferences.data.groups}
        saving={savePreferences.isPending}
        onSave={saveGroups}
        onCancel={preferences.data.completed ? () => setEditingGroups(false) : undefined}
      />
    );
  }

  const ratedHere = Object.keys(ratings).length;
  const canUndo = changes.length > 0 || previousPage !== null;

  return (
    <div className="flex flex-1 flex-col">
      <main className="mx-auto w-full max-w-[1296px] flex-1 px-8 py-6">
        <div className="mb-[18px] flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <div>
            <h1 className="font-display text-[28px] font-bold">İzlediklerine yıldız ver</h1>
            <p className="mt-1 text-sm text-neutral-400">
              Dokunmadıkların "izlemedim" sayılır, tek tek işaretlemene gerek yok.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setEditingGroups(true)}
            className="text-[13px] text-neutral-400 hover:text-white"
          >
            Zevk gruplarımı değiştir
          </button>
        </div>

        {error && <p className="mb-3 text-sm text-red-300">{error}</p>}

        {exhausted ? (
          <p className="py-16 text-center text-neutral-400">Gösterilecek film kalmadı.</p>
        ) : (
          <div
            className={`grid grid-cols-[repeat(auto-fill,minmax(158px,1fr))] gap-4 transition-opacity ${
              busy && cards.length > 0 ? "opacity-50" : ""
            }`}
          >
            {cards.length === 0
              ? Array.from({ length: SKELETON_CARDS }, (_, i) => (
                  <div key={i} className="aspect-[2/3] animate-pulse rounded-[10px] bg-neutral-800" />
                ))
              : cards.map((card) => {
                  const score = ratings[card.tmdb_id];
                  return (
                    <article
                      key={card.tmdb_id}
                      onMouseEnter={() => (hovered.current = card.tmdb_id)}
                      onMouseLeave={() => (hovered.current = null)}
                    >
                      <Poster
                        path={card.poster_path}
                        title={card.title_tr}
                        eager
                        className={score ? "ring-[3px] ring-amber-400" : ""}
                      />
                      <p className="mt-2 truncate text-[13px] font-medium" title={card.title_tr}>
                        {card.title_tr}
                      </p>
                      <p className="truncate text-xs text-neutral-400">
                        {[card.year, card.directors[0]].filter(Boolean).join(" · ")}
                      </p>
                      <Stars
                        title={card.title_tr}
                        value={score}
                        onRate={(s) => rate(card.tmdb_id, s)}
                      />
                    </article>
                  );
                })}
          </div>
        )}
      </main>

      <footer className="sticky bottom-0 border-t border-neutral-800 bg-neutral-900 px-8 py-3">
        <div className="mx-auto flex max-w-[1232px] flex-wrap items-center gap-x-5 gap-y-3">
          <p className="text-sm">
            <strong className="text-amber-400">{ratedHere} film</strong> puanlandı,{" "}
            <span className="text-neutral-400">
              {cards.length - ratedHere} film izlemedim sayılacak
            </span>
          </p>
          <span className="hidden text-xs text-neutral-500 lg:inline">
            Üstüne gel ve 1-5 · Enter sonraki · Z geri al
          </span>
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={() => void undo()}
              disabled={!canUndo || busy}
              className="h-11 rounded-[10px] border border-neutral-700 px-4 hover:bg-neutral-800 disabled:opacity-40"
            >
              Geri al
            </button>
            <button
              type="button"
              onClick={() => void goNext()}
              disabled={busy || cards.length === 0}
              className="h-11 rounded-[10px] bg-amber-400 px-6 font-semibold text-neutral-950 hover:bg-amber-300 disabled:opacity-60"
            >
              {busy ? "Hazırlanıyor…" : `Sonraki ${cards.length || SKELETON_CARDS} film`}
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
