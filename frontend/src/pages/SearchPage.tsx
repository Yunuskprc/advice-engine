import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { SearchResult } from "../api/types";
import Poster from "../components/Poster";
import StarRating from "../components/StarRating";
import { useRateMovie, useToggleWatchlist } from "../hooks/useLibrary";

const DEBOUNCE_MS = 250;

function ResultRow({ movie }: { movie: SearchResult }) {
  const rate = useRateMovie();
  const watchlist = useToggleWatchlist();
  const id = movie.tmdb_id;

  return (
    <li className="flex gap-3 py-3">
      <Link to={`/film/${id}`} className="w-16 shrink-0">
        <Poster path={movie.poster_path} title={movie.title_tr} />
      </Link>
      <div className="min-w-0 flex-1 space-y-1">
        <Link to={`/film/${id}`} className="block truncate font-medium hover:text-amber-300">
          {movie.title_tr}
        </Link>
        <p className="truncate text-xs text-neutral-400">
          {[movie.year, movie.title_original !== movie.title_tr && movie.title_original]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <div className="flex items-center gap-4">
          <StarRating
            value={movie.my_rating}
            onChange={(score) =>
              rate.mutate({ id, score: score === movie.my_rating ? null : score })
            }
          />
          <button
            type="button"
            onClick={() => watchlist.mutate({ id, inList: movie.in_watchlist })}
            className="text-xs text-amber-400 hover:text-amber-300"
          >
            {movie.in_watchlist ? "Listemden çıkar" : "Listeme ekle"}
          </button>
        </div>
      </div>
    </li>
  );
}

export default function SearchPage() {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setQuery(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [text]);

  const results = useQuery({
    queryKey: ["search", query],
    queryFn: () => api.search(query),
    enabled: query.length > 0,
    placeholderData: keepPreviousData,
  });

  return (
    <main className="mx-auto max-w-xl space-y-4 px-4 py-6">
      <input
        type="search"
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Film ara (Türkçe veya orijinal başlık)"
        className="w-full rounded-xl border border-neutral-700 bg-neutral-900 px-4 py-3 outline-none focus:border-amber-400"
      />
      {results.isError && <p className="text-sm text-red-300">Arama yapılamadı.</p>}
      {query && results.data?.length === 0 && (
        <p className="text-sm text-neutral-400">Sonuç bulunamadı.</p>
      )}
      {query && (
        <ul className="divide-y divide-neutral-800">
          {results.data?.map((m) => <ResultRow key={m.tmdb_id} movie={m} />)}
        </ul>
      )}
    </main>
  );
}
