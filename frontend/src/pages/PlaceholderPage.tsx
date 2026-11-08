export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <main className="mx-auto max-w-xl px-4 py-6">
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="mt-2 text-sm text-neutral-400">Bu ekran henüz hazır değil.</p>
    </main>
  );
}
