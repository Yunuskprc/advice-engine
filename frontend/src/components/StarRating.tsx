const SCORES = [1, 2, 3, 4, 5] as const;

export default function StarRating({
  value,
  onChange,
  large = false,
}: {
  value: number | null;
  onChange: (score: number) => void;
  large?: boolean;
}) {
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Puan">
      {SCORES.map((score) => (
        <button
          key={score}
          type="button"
          onClick={() => onChange(score)}
          aria-label={`${score} yıldız`}
          aria-pressed={value === score}
          className={`leading-none transition-colors ${large ? "text-4xl" : "text-xl"} ${
            value !== null && score <= value
              ? "text-amber-400"
              : "text-neutral-600 hover:text-amber-300"
          }`}
        >
          ★
        </button>
      ))}
    </div>
  );
}
