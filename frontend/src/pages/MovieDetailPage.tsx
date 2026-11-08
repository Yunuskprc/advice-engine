import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { WatchProvider } from "../api/types";
import Poster, { imageUrl } from "../components/Poster";
import StarRating from "../components/StarRating";
import { useRateMovie, useToggleWatchlist } from "../hooks/useLibrary";

const BACKDROP_SIZE = "w780";
const LOGO_SIZE = "w92";
const PROVIDER_LABELS: Record<string, string> = {
  flatrate: "Abonelik",
  rent: "Kiralık",
  buy: "Satın al",
};

function Providers({ providers }: { providers: WatchProvider[] }) {
  if (providers.length === 0) return null;
  const groups = Object.keys(PROVIDER_LABELS).filter((t) => providers.some((p) => p.type === t));
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-neutral-400">Türkiye'de nerede izlenir</h2>
      {groups.map((type) => (
        <div key={type} className="flex items-center gap-2">
          <span className="w-16 text-xs text-neutral-500">{PROVIDER_LABELS[type]}</span>
          <div className="flex flex-wrap gap-1.5">
            {providers
              .filter((p) => p.type === type)
              .map((p) =>
                p.logo_path ? (
                  <img
                    key={p.id}
                    src={imageUrl(LOGO_SIZE, p.logo_path)}
                    alt={p.name}
                    title={p.name}
                    loading="lazy"
                    className="size-8 rounded-md"
                  />
                ) : (
                  <span key={p.id} className="text-xs text-neutral-300">
                    {p.name}
                  </span>
                ),
              )}
          </div>
        </div>
      ))}
    </section>
  );
}

export default function MovieDetailPage() {
  const id = Number(useParams().id);
  const rate = useRateMovie();
  const watchlist = useToggleWatchlist();

  const movie = useQuery({
    queryKey: ["movie", id],
    queryFn: () => api.movie(id),
    retry: false,
  });
  const similar = useQuery({
    queryKey: ["similar", id],
    queryFn: () => api.similar(id),
    retry: false,
  });

  if (movie.isPending) return <p className="p-6 text-neutral-400">Yükleniyor…</p>;
  if (movie.isError) return <p className="p-6 text-red-300">Film bulunamadı.</p>;
  const m = movie.data;

  return (
    <main className="mx-auto max-w-3xl pb-10">
      {m.backdrop_path && (
        <img
          src={imageUrl(BACKDROP_SIZE, m.backdrop_path)}
          alt=""
          className="aspect-video w-full object-cover sm:rounded-b-2xl"
        />
      )}
      <div className="space-y-5 px-4 pt-5">
        <header>
          <h1 className="text-2xl font-bold">{m.title_tr}</h1>
          <p className="text-sm text-neutral-400">
            {[
              m.title_original !== m.title_tr && m.title_original,
              m.year,
              m.runtime && `${m.runtime} dk`,
              m.vote_average && `TMDB ${m.vote_average.toFixed(1)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </header>

        <div className="flex items-center gap-4">
          <StarRating
            value={m.my_rating}
            onChange={(score) =>
              rate.mutate({ id, score: score === m.my_rating ? null : score })
            }
            large
          />
          <button
            type="button"
            onClick={() => watchlist.mutate({ id, inList: m.in_watchlist })}
            className="rounded-xl border border-neutral-700 px-4 py-2 text-sm hover:bg-neutral-800"
          >
            {m.in_watchlist ? "Listemden çıkar" : "Listeme ekle"}
          </button>
        </div>

        {m.overview && <p className="leading-relaxed text-neutral-200">{m.overview}</p>}

        <dl className="space-y-1 text-sm">
          {m.directors.length > 0 && (
            <div>
              <dt className="inline text-neutral-500">Yönetmen: </dt>
              <dd className="inline">{m.directors.map((p) => p.name).join(", ")}</dd>
            </div>
          )}
          {m.cast.length > 0 && (
            <div>
              <dt className="inline text-neutral-500">Oyuncular: </dt>
              <dd className="inline">{m.cast.map((p) => p.name).join(", ")}</dd>
            </div>
          )}
          {m.genres.length > 0 && (
            <div>
              <dt className="inline text-neutral-500">Türler: </dt>
              <dd className="inline">{m.genres.join(", ")}</dd>
            </div>
          )}
        </dl>

        {m.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {m.keywords.map((k) => (
              <span key={k} className="rounded-full bg-neutral-800 px-2.5 py-0.5 text-xs">
                {k}
              </span>
            ))}
          </div>
        )}

        <Providers providers={m.providers} />

        {similar.data && similar.data.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-neutral-400">Buna benzer filmler</h2>
            <ul className="grid grid-cols-3 gap-3 sm:grid-cols-5">
              {similar.data.map((s) => (
                <li key={s.tmdb_id}>
                  <Link to={`/film/${s.tmdb_id}`} className="block space-y-1">
                    <Poster path={s.poster_path} title={s.title_tr} />
                    <p className="truncate text-xs">{s.title_tr}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}
