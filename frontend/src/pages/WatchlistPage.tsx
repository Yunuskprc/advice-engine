import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { WatchlistItem } from "../api/types";
import Poster from "../components/Poster";
import ProviderLogos from "../components/ProviderLogos";
import RateDialog from "../components/RateDialog";
import { useToggleWatchlist } from "../hooks/useLibrary";
import { useMarkWatched, useWatchlist } from "../hooks/useRecommendations";

const ALL = "all";

export default function WatchlistPage() {
  const list = useWatchlist();
  const remove = useToggleWatchlist();
  const markWatched = useMarkWatched();
  const [provider, setProvider] = useState(ALL);
  const [rating, setRating] = useState<WatchlistItem | null>(null);

  const providerOptions = useMemo(() => {
    const seen = new Map<number, string>();
    list.data?.forEach((m) => m.providers.forEach((p) => seen.set(p.id, p.name)));
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1], "tr"));
  }, [list.data]);

  const items =
    list.data?.filter(
      (m) => provider === ALL || m.providers.some((p) => String(p.id) === provider),
    ) ?? [];

  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Listem</h1>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          aria-label="Platform filtresi"
          className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm"
        >
          <option value={ALL}>Tüm platformlar</option>
          {providerOptions.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {list.isError && <p className="text-sm text-red-300">Liste alınamadı.</p>}
      {list.data?.length === 0 && (
        <p className="py-10 text-center text-neutral-400">Listeniz boş.</p>
      )}

      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((m) => (
          <li
            key={m.tmdb_id}
            className="flex gap-3 rounded-2xl border border-neutral-800 bg-neutral-900 p-3"
          >
            <Link to={`/film/${m.tmdb_id}`} className="w-20 shrink-0">
              <Poster path={m.poster_path} title={m.title_tr} />
            </Link>
            <div className="min-w-0 flex-1 space-y-2">
              <Link to={`/film/${m.tmdb_id}`} className="block font-semibold hover:text-amber-300">
                {m.title_tr}
              </Link>
              <p className="text-xs text-neutral-400">
                {[m.year, m.runtime && `${m.runtime} dk`].filter(Boolean).join(" · ")}
              </p>
              <ProviderLogos providers={m.providers} />
              <div className="flex flex-wrap gap-1.5 text-xs">
                <button
                  type="button"
                  onClick={() => setRating(m)}
                  className="rounded-lg bg-amber-400 text-neutral-950 px-3 py-1.5 hover:bg-amber-300"
                >
                  İzledim, puanla
                </button>
                <button
                  type="button"
                  onClick={() => remove.mutate({ id: m.tmdb_id, inList: true })}
                  className="rounded-lg border border-neutral-700 px-3 py-1.5 hover:bg-neutral-800"
                >
                  Çıkar
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {rating && (
        <RateDialog
          title={rating.title_tr}
          onClose={() => setRating(null)}
          onRate={(score) => {
            markWatched.mutate({ id: rating.tmdb_id, score });
            setRating(null);
          }}
        />
      )}
    </main>
  );
}
