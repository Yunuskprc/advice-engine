import StarRating from "./StarRating";

export default function RateDialog({
  title,
  onRate,
  onClose,
}: {
  title: string;
  onRate: (score: number) => void;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${title} için puan`}
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="space-y-4 rounded-2xl border border-neutral-700 bg-neutral-900 p-6 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-medium">{title}</p>
        <StarRating value={null} onChange={onRate} large />
        <button type="button" onClick={onClose} className="text-sm text-neutral-400">
          Vazgeç
        </button>
      </div>
    </div>
  );
}
