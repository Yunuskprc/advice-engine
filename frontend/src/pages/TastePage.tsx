import { Link } from "react-router";
import { clusterTitle } from "../api/labels";
import type { TasteCluster } from "../api/types";
import Poster from "../components/Poster";
import { useRecomputeTaste, useTaste } from "../hooks/useLibrary";

function Insight({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-[14px] bg-neutral-900 p-[18px]">
      <p className="text-[13px] text-neutral-400">{label}</p>
      <p className="mt-1.5 font-display text-2xl font-bold">{value}</p>
      <p className="mt-1 text-sm text-neutral-300">{note}</p>
    </div>
  );
}

function ClusterCard({ cluster, share }: { cluster: TasteCluster; share: number }) {
  const percent = Math.round(share * 100);
  return (
    <article className="flex flex-col gap-3 rounded-[14px] bg-neutral-900 p-[18px]">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-lg font-semibold">{clusterTitle(cluster)}</h3>
        <Link
          to={`/?cluster=${cluster.id}`}
          className="shrink-0 text-[13px] font-semibold text-amber-400 hover:text-amber-300"
        >
          Bu kümeden öner
        </Link>
      </div>
      {cluster.description && <p className="text-sm text-neutral-300">{cluster.description}</p>}
      <div
        className="h-2 overflow-hidden rounded bg-neutral-800"
        role="img"
        aria-label={`Zevkinin yüzde ${percent} kadarı`}
      >
        <div className="h-full bg-amber-400" style={{ width: `${percent}%` }} />
      </div>
      <ul className="grid grid-cols-5 gap-2">
        {cluster.typical.map((m) => (
          <li key={m.tmdb_id}>
            <Link to={`/film/${m.tmdb_id}`} title={m.title_tr}>
              <Poster path={m.poster_path} title={m.title_tr} className="rounded-md" />
            </Link>
          </li>
        ))}
      </ul>
    </article>
  );
}

export default function TastePage() {
  const taste = useTaste();
  const recompute = useRecomputeTaste();
  const data = taste.data;
  const totalWeight = data?.clusters.reduce((sum, c) => sum + c.weight, 0) ?? 0;
  const insights = data?.insights;

  return (
    <main className="mx-auto w-full max-w-[1200px] px-8 pt-8 pb-14">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-[32px] font-bold">Seni böyle tanıyoruz</h1>
          {insights && (
            <p className="mt-1.5 text-[15px] text-neutral-400">
              {insights.rated} puan ve {insights.skipped} "izlemedim" cevabından çıkarıldı.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => recompute.mutate()}
          disabled={recompute.isPending}
          className="h-11 rounded-[10px] border border-neutral-700 px-4 text-sm hover:bg-neutral-800 disabled:opacity-50"
        >
          Zevkimi yeniden hesapla
        </button>
      </div>

      {taste.isError && <p className="mt-4 text-sm text-red-300">Zevk haritası alınamadı.</p>}

      {insights && (insights.favorites.length > 0 || insights.avoid.length > 0) && (
        <section
          aria-label="İzleme alışkanlıkların"
          className="mt-7 grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3.5"
        >
          {insights.favorites.length > 0 && (
            <Insight
              label="En çok izlediğin"
              value={insights.favorites.join(", ")}
              note="Bu türleri ortalamanın üzerinde izliyorsun."
            />
          )}
          <Insight
            label="Türk filmleri"
            value={`Her ${insights.turkish_every} kartta bir`}
            note="Sıklık, izleme alışkanlığına göre ayarlanıyor."
          />
          {insights.avoid.length > 0 && (
            <Insight
              label="Az gösterdiklerimiz"
              value={insights.avoid.join(", ")}
              note="Bunlardan neredeyse hiç izlememişsin."
            />
          )}
        </section>
      )}

      {data && data.positive_count < data.min_positive && (
        <p className="mt-7 text-sm text-neutral-400">
          Kümeler için en az {data.min_positive} filme 4 veya 5 yıldız ver (şu an{" "}
          {data.positive_count}). O zamana kadar tek bir genel zevk kullanılıyor.
        </p>
      )}

      {data?.clusters.length === 0 && data.negatives.length === 0 && (
        <p className="py-10 text-center text-neutral-400">
          Henüz zevk haritası yok.{" "}
          <Link to="/puanla" className="text-amber-400 hover:text-amber-300">
            Puanlamaya başla
          </Link>
          .
        </p>
      )}

      {data && data.clusters.length > 0 && (
        <>
          <h2 className="mt-9 mb-3.5 font-display text-[22px] font-bold">Zevk kümelerin</h2>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(480px,100%),1fr))] gap-3.5">
            {data.clusters.map((c) => (
              <ClusterCard key={c.id} cluster={c} share={totalWeight ? c.weight / totalWeight : 0} />
            ))}
          </div>
        </>
      )}

      {data && data.negatives.length > 0 && (
        <>
          <h2 className="mt-9 mb-3.5 font-display text-[22px] font-bold">Uzak durduğun</h2>
          <div className="flex flex-wrap gap-2.5">
            {data.negatives.map((c) => (
              <span key={c.id} className="rounded-full bg-neutral-900 px-4 py-2.5 text-sm">
                {clusterTitle(c)}
              </span>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
