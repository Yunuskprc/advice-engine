import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import { clusterTitle } from "../api/labels";
import type { FeedbackAction, RecommendationFilters, RecommendedMovie } from "../api/types";
import { useRateMovie, useTaste } from "../hooks/useLibrary";
import {
  useFeedback,
  useRecommendationOptions,
  useRecommendations,
} from "../hooks/useRecommendations";
import FilterPanel, { EMPTY_FILTERS } from "./FilterPanel";
import Poster from "./Poster";
import ProviderLogos from "./ProviderLogos";
import RateDialog from "./RateDialog";

const LEVELS = [
  { label: "Güvenli", value: 0 },
  { label: "Dengeli", value: 0.5 },
  { label: "Maceracı", value: 1 },
];
const SKELETON_CARDS = 6;

type Toast = { movie: RecommendedMovie; action: FeedbackAction; text: string };

function metaLine(movie: RecommendedMovie): string {
  return [movie.year, movie.runtime && `${movie.runtime} dk`].filter(Boolean).join(" · ");
}

function activeFilterCount(filters: RecommendationFilters): number {
  return [
    filters.year_min,
    filters.year_max,
    filters.runtime_min,
    filters.runtime_max,
    filters.origin !== "all" ? filters.origin : null,
    filters.genres_include.length || null,
    filters.genres_exclude.length || null,
    filters.providers.length || null,
  ].filter((v) => v !== null).length;
}

function Hero({
  movie,
  onSave,
  onWatched,
  onDismiss,
}: {
  movie: RecommendedMovie;
  onSave: () => void;
  onWatched: () => void;
  onDismiss: () => void;
}) {
  const secondary = "h-11 rounded-[10px] border border-neutral-700 px-[18px] hover:bg-neutral-800";
  return (
    <section className="flex flex-wrap gap-6 rounded-2xl bg-neutral-900 p-5">
      <Link to={`/film/${movie.tmdb_id}`} className="w-[200px] shrink-0">
        <Poster path={movie.poster_path} title={movie.title_tr} eager />
      </Link>
      <div className="flex min-w-0 flex-[999_1_320px] flex-col gap-2.5">
        <p className="text-[13px] font-semibold text-amber-400">Bugünün en iyi eşleşmesi</p>
        <Link
          to={`/film/${movie.tmdb_id}`}
          className="font-display text-4xl leading-tight font-bold hover:text-amber-300"
        >
          {movie.title_tr}
        </Link>
        <p className="text-sm text-neutral-400">{metaLine(movie)}</p>
        <ProviderLogos providers={movie.providers} />
        <p className="mt-1.5 max-w-[640px] text-lg leading-snug">{movie.explanation}</p>
        <div className="mt-auto flex flex-wrap gap-2 pt-3">
          <button
            type="button"
            onClick={onSave}
            className="h-11 rounded-[10px] bg-amber-400 px-[22px] font-semibold text-neutral-950 hover:bg-amber-300"
          >
            Listeme ekle
          </button>
          <button type="button" onClick={onWatched} className={secondary}>
            İzledim
          </button>
          <button type="button" onClick={onDismiss} className={secondary}>
            İlgimi çekmedi
          </button>
        </div>
      </div>
    </section>
  );
}

function Card({
  movie,
  onSave,
  onWatched,
  onDismiss,
}: {
  movie: RecommendedMovie;
  onSave: () => void;
  onWatched: () => void;
  onDismiss: () => void;
}) {
  const action = "h-11 rounded-lg px-2.5 text-[13px] hover:bg-neutral-800";
  return (
    <article className="flex gap-3 rounded-xl bg-neutral-900 p-3">
      <Link to={`/film/${movie.tmdb_id}`} className="w-[84px] shrink-0">
        <Poster path={movie.poster_path} title={movie.title_tr} className="rounded-lg" />
      </Link>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <Link to={`/film/${movie.tmdb_id}`} className="text-[15px] font-semibold hover:text-amber-300">
          {movie.title_tr}
        </Link>
        <p className="text-xs text-neutral-400">{metaLine(movie)}</p>
        <ProviderLogos providers={movie.providers} />
        <p className="mt-1 text-[13px] leading-snug text-neutral-300">{movie.explanation}</p>
        <div className="mt-auto flex flex-wrap gap-0.5 pt-1.5">
          <button type="button" onClick={onSave} className={`${action} text-amber-400`}>
            Listeme ekle
          </button>
          <button type="button" onClick={onWatched} className={`${action} text-neutral-300`}>
            İzledim
          </button>
          <button type="button" onClick={onDismiss} className={`${action} text-neutral-400`}>
            İlgimi çekmedi
          </button>
        </div>
      </div>
    </article>
  );
}

export default function Recommendations() {
  const [params, setParams] = useSearchParams();
  const clusterParam = params.get("cluster");
  const clusterId = clusterParam === null ? null : Number(clusterParam);

  const taste = useTaste();
  const options = useRecommendationOptions();
  const feedback = useFeedback();
  const rate = useRateMovie();

  const [filters, setFilters] = useState<RecommendationFilters>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [exploration, setExploration] = useState(0);
  const [exclude, setExclude] = useState<number[]>([]);
  const [nonce, setNonce] = useState(0);
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const [rating, setRating] = useState<RecommendedMovie | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  useEffect(() => {
    setExclude([]);
    setHidden(new Set());
    setToast(null);
  }, [clusterId, filters, exploration]);

  const request = useMemo(
    () => ({ cluster_id: clusterId, filters, exploration, exclude }),
    [clusterId, filters, exploration, exclude],
  );
  const result = useRecommendations(request, nonce);
  const items = useMemo(
    () => result.data?.items.filter((m) => !hidden.has(m.tmdb_id)) ?? [],
    [result.data, hidden],
  );
  const activeCluster = result.data?.cluster_id ?? null;

  const hide = (id: number, show = false) =>
    setHidden((current) => {
      const next = new Set(current);
      if (show) next.delete(id);
      else next.add(id);
      return next;
    });

  const giveFeedback = (movie: RecommendedMovie, action: FeedbackAction, text: string) => {
    hide(movie.tmdb_id);
    feedback.mutate({ id: movie.tmdb_id, action, clusterId: activeCluster });
    setToast({ movie, action, text });
  };

  const undoToast = () => {
    if (!toast) return;
    hide(toast.movie.tmdb_id, true);
    void api.undoFeedback(toast.movie.tmdb_id, toast.action);
    setToast(null);
  };

  const refresh = () => {
    setExclude((e) => [...e, ...(result.data?.items.map((m) => m.tmdb_id) ?? [])]);
    setHidden(new Set());
    setToast(null);
  };

  const selectCluster = (id: number | null) => {
    if (id === null) {
      setParams({});
      setNonce((n) => n + 1); // Her "Beni şaşırt" yeni bir küme çeker.
    } else {
      setParams({ cluster: String(id) });
    }
  };

  const clusters = taste.data?.clusters ?? [];
  const filterCount = activeFilterCount(filters);
  const chip = (active: boolean) =>
    `h-11 shrink-0 rounded-full border px-4 text-sm font-medium transition-colors ${
      active
        ? "border-amber-400 bg-[#2a2415] text-amber-400"
        : "border-neutral-700 text-neutral-300 hover:border-neutral-600"
    }`;

  if (taste.data && clusters.length === 0) {
    return (
      <div className="rounded-2xl bg-neutral-900 p-10 text-center">
        <p className="font-display text-2xl font-bold">Sana film önermek için seni tanıyalım</p>
        <p className="mt-2 text-neutral-400">Birkaç filme 4 veya 5 yıldız ver, önerilerin burada belirsin.</p>
        <Link
          to="/puanla"
          className="mt-5 inline-flex h-11 items-center rounded-[10px] bg-amber-400 px-6 font-semibold text-neutral-950 hover:bg-amber-300"
        >
          Puanlamaya başla
        </Link>
      </div>
    );
  }

  const [hero, ...rest] = items;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {clusters.map((c) => (
          <button
            key={c.id}
            type="button"
            aria-pressed={clusterId === c.id}
            className={chip(clusterId === c.id)}
            onClick={() => selectCluster(c.id)}
          >
            {clusterTitle(c)}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={clusterId === null}
          className={chip(clusterId === null)}
          onClick={() => selectCluster(null)}
        >
          Beni şaşırt
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 text-sm text-neutral-400">
        <span>Keşif</span>
        <div className="flex rounded-[10px] bg-neutral-900 p-[3px]" role="group" aria-label="Keşif seviyesi">
          {LEVELS.map((l) => (
            <button
              key={l.label}
              type="button"
              aria-pressed={exploration === l.value}
              onClick={() => setExploration(l.value)}
              className={`h-[38px] rounded-lg px-3.5 text-[13px] font-medium ${
                exploration === l.value ? "bg-neutral-700 text-white" : "text-neutral-400"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          aria-expanded={showFilters}
          onClick={() => setShowFilters((s) => !s)}
          className="h-11 rounded-[10px] border border-neutral-700 px-3.5 text-neutral-100 hover:bg-neutral-800"
        >
          {filterCount > 0 ? `Filtreler · ${filterCount}` : "Filtreler"}
        </button>
        <button
          type="button"
          onClick={refresh}
          disabled={!result.data || result.data.items.length === 0}
          className="ml-auto h-11 rounded-[10px] px-3.5 font-semibold text-amber-400 hover:bg-neutral-800 disabled:opacity-40"
        >
          Başka öneriler
        </button>
      </div>

      {showFilters && (
        <FilterPanel
          value={filters}
          genres={options.data?.genres ?? []}
          providers={options.data?.providers ?? []}
          onApply={setFilters}
        />
      )}

      {result.isError && <p className="text-sm text-red-300">Öneriler alınamadı.</p>}

      {result.isPending && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
          {Array.from({ length: SKELETON_CARDS }, (_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-neutral-900" />
          ))}
        </div>
      )}

      {result.data && items.length === 0 && (
        <p className="py-8 text-center text-neutral-400">Bu seçimlerle öneri bulunamadı.</p>
      )}

      <div className={`space-y-6 transition-opacity ${result.isPlaceholderData ? "opacity-60" : ""}`}>
        {hero && (
          <Hero
            movie={hero}
            onSave={() => giveFeedback(hero, "saved", `${hero.title_tr} listene eklendi`)}
            onWatched={() => setRating(hero)}
            onDismiss={() => giveFeedback(hero, "dismissed", `${hero.title_tr} gizlendi`)}
          />
        )}
        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
          {rest.map((m) => (
            <Card
              key={m.tmdb_id}
              movie={m}
              onSave={() => giveFeedback(m, "saved", `${m.title_tr} listene eklendi`)}
              onWatched={() => setRating(m)}
              onDismiss={() => giveFeedback(m, "dismissed", `${m.title_tr} gizlendi`)}
            />
          ))}
        </div>
      </div>

      {toast && (
        <div
          role="status"
          className="sticky bottom-4 mx-auto flex w-fit items-center gap-4 rounded-xl bg-neutral-100 py-2 pr-2 pl-[18px] text-sm text-neutral-950"
        >
          <span>{toast.text}</span>
          <button
            type="button"
            onClick={undoToast}
            className="h-11 rounded-lg bg-neutral-950 px-3.5 font-semibold text-white"
          >
            Geri al
          </button>
        </div>
      )}

      {rating && (
        <RateDialog
          title={rating.title_tr}
          onClose={() => setRating(null)}
          onRate={(score) => {
            const id = rating.tmdb_id;
            setRating(null);
            hide(id);
            rate.mutate({ id, score });
            feedback.mutate({ id, action: "watched", clusterId: activeCluster });
          }}
        />
      )}
    </div>
  );
}
