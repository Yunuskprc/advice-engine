import type { Job } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import { useHealth, useJobs, useSubmitDemoJob } from "../hooks/useStatus";

const STATUS_TR: Record<Job["status"], string> = {
  queued: "Kuyrukta",
  running: "Çalışıyor",
  done: "Bitti",
  failed: "Başarısız",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-400">
        {title}
      </h2>
      {children}
    </section>
  );
}

function JobRow({ job }: { job: Job }) {
  const pct = job.total ? Math.round((job.progress / job.total) * 100) : 0;
  return (
    <li className="space-y-1.5 py-2">
      <div className="flex items-center justify-between text-sm">
        <span>
          #{job.id} <span className="text-neutral-400">{job.type}</span>
        </span>
        <span className="text-neutral-400">
          {STATUS_TR[job.status]}
          {job.total ? ` · ${job.progress}/${job.total}` : ""}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-neutral-800">
        <div
          className={`h-full transition-all ${job.status === "failed" ? "bg-red-500" : "bg-sky-500"}`}
          style={{ width: `${job.status === "done" ? 100 : pct}%` }}
        />
      </div>
      {job.error && <p className="text-xs text-red-300">{job.error}</p>}
    </li>
  );
}

export default function StatusPage() {
  const health = useHealth();
  const jobs = useJobs();
  const submit = useSubmitDemoJob();
  const h = health.data;

  return (
    <main className="mx-auto max-w-xl space-y-4 px-4 py-6">
      <h1 className="text-2xl font-bold">Film Öneri</h1>

      <Card title="Sistem durumu">
        {health.isPending && <p className="text-neutral-400">Kontrol ediliyor…</p>}
        {health.isError && <p className="text-red-300">API'ye ulaşılamadı.</p>}
        {h && (
          <dl className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <dt>DuckDB {h.db.version}</dt>
              <StatusBadge ok={h.db.ok} label={h.db.ok ? h.db.extensions.join(", ") : "Hata"} />
            </div>
            <div className="flex items-center justify-between">
              <dt>Ollama</dt>
              <StatusBadge ok={h.ollama.reachable} label={h.ollama.reachable ? "Bağlı" : "Kapalı"} />
            </div>
            <div className="flex items-center justify-between pl-3 text-neutral-400">
              <dt>{h.ollama.embed_model}</dt>
              <StatusBadge ok={h.ollama.embed_model_present} label={h.ollama.embed_model_present ? "Var" : "Yok"} />
            </div>
            <div className="flex items-center justify-between pl-3 text-neutral-400">
              <dt>{h.ollama.chat_model}</dt>
              <StatusBadge ok={h.ollama.chat_model_present} label={h.ollama.chat_model_present ? "Var" : "Yok"} />
            </div>
            {(h.db.error ?? h.ollama.error) && (
              <p className="text-xs text-red-300">{h.db.error ?? h.ollama.error}</p>
            )}
          </dl>
        )}
        <button
          onClick={() => health.refetch()}
          className="mt-4 text-xs text-sky-400 active:text-sky-300"
        >
          Yeniden kontrol et
        </button>
      </Card>

      <Card title="İşler">
        <button
          onClick={() => submit.mutate()}
          disabled={submit.isPending}
          className="mb-2 w-full rounded-xl bg-sky-600 py-3 font-medium active:bg-sky-700 disabled:opacity-50"
        >
          Demo işi başlat
        </button>
        {jobs.data?.length === 0 && <p className="text-sm text-neutral-400">Henüz iş yok.</p>}
        <ul className="divide-y divide-neutral-800">
          {jobs.data?.map((j) => <JobRow key={j.id} job={j} />)}
        </ul>
      </Card>
    </main>
  );
}
