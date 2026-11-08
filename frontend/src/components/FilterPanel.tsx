import { useState } from "react";
import type { FilterOption, RecommendationFilters } from "../api/types";

export const EMPTY_FILTERS: RecommendationFilters = {
  year_min: null,
  year_max: null,
  runtime_min: null,
  runtime_max: null,
  origin: "all",
  genres_include: [],
  genres_exclude: [],
  providers: [],
};

const ORIGINS: { value: RecommendationFilters["origin"]; label: string }[] = [
  { value: "all", label: "Hepsi" },
  { value: "domestic", label: "Yerli" },
  { value: "foreign", label: "Yabancı" },
];

const NUMBER_FIELDS: { key: keyof RecommendationFilters; label: string }[] = [
  { key: "year_min", label: "Yıl (en az)" },
  { key: "year_max", label: "Yıl (en çok)" },
  { key: "runtime_min", label: "Süre dk (en az)" },
  { key: "runtime_max", label: "Süre dk (en çok)" },
];

function chipClass(active: boolean, negative = false): string {
  if (negative) return "bg-red-500/20 text-red-300";
  return active ? "bg-amber-400 text-neutral-950" : "bg-neutral-800 text-neutral-300";
}

export default function FilterPanel({
  value,
  genres,
  providers,
  onApply,
}: {
  value: RecommendationFilters;
  genres: FilterOption[];
  providers: FilterOption[];
  onApply: (filters: RecommendationFilters) => void;
}) {
  const [draft, setDraft] = useState(value);

  // Tür çipi üç durumlu: seçili değil → dahil → hariç → seçili değil.
  const cycleGenre = (id: number) =>
    setDraft((d) => {
      if (d.genres_include.includes(id)) {
        return {
          ...d,
          genres_include: d.genres_include.filter((x) => x !== id),
          genres_exclude: [...d.genres_exclude, id],
        };
      }
      if (d.genres_exclude.includes(id)) {
        return { ...d, genres_exclude: d.genres_exclude.filter((x) => x !== id) };
      }
      return { ...d, genres_include: [...d.genres_include, id] };
    });

  const toggleProvider = (id: number) =>
    setDraft((d) => ({
      ...d,
      providers: d.providers.includes(id)
        ? d.providers.filter((x) => x !== id)
        : [...d.providers, id],
    }));

  return (
    <section className="space-y-4 rounded-2xl border border-neutral-800 bg-neutral-900 p-4 text-sm">
      <div className="flex gap-2">
        {ORIGINS.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => setDraft((d) => ({ ...d, origin: o.value }))}
            className={`rounded-full px-3 py-1 ${chipClass(draft.origin === o.value)}`}
          >
            {o.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {NUMBER_FIELDS.map((f) => (
          <label key={f.key} className="space-y-1 text-xs text-neutral-400">
            <span>{f.label}</span>
            <input
              type="number"
              value={(draft[f.key] as number | null) ?? ""}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  [f.key]: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-neutral-100"
            />
          </label>
        ))}
      </div>

      <div className="space-y-1.5">
        <p className="text-xs text-neutral-400">Türler (bir tık dahil, iki tık hariç)</p>
        <div className="flex flex-wrap gap-1.5">
          {genres.map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => cycleGenre(g.id)}
              className={`rounded-full px-2.5 py-0.5 text-xs ${chipClass(
                draft.genres_include.includes(g.id),
                draft.genres_exclude.includes(g.id),
              )}`}
            >
              {g.name}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <p className="text-xs text-neutral-400">Türkiye'de şu platformlarda olsun</p>
        <div className="flex flex-wrap gap-1.5">
          {providers.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => toggleProvider(p.id)}
              className={`rounded-full px-2.5 py-0.5 text-xs ${chipClass(
                draft.providers.includes(p.id),
              )}`}
            >
              {p.name}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onApply(draft)}
          className="flex-1 rounded-xl bg-amber-400 text-neutral-950 py-2 font-medium hover:bg-amber-300"
        >
          Uygula
        </button>
        <button
          type="button"
          onClick={() => {
            setDraft(EMPTY_FILTERS);
            onApply(EMPTY_FILTERS);
          }}
          className="rounded-xl border border-neutral-700 px-4 py-2 hover:bg-neutral-800"
        >
          Temizle
        </button>
      </div>
    </section>
  );
}
