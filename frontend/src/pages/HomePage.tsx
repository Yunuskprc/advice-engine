import Recommendations from "../components/Recommendations";

export default function HomePage() {
  return (
    <main className="mx-auto w-full max-w-[1296px] px-8 pt-6 pb-12">
      <h1 className="mb-3.5 font-display text-[28px] font-bold">Bu akşam ne izlesen?</h1>
      <Recommendations />
    </main>
  );
}
