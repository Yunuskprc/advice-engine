const IMAGE_BASE = "https://image.tmdb.org/t/p";
const POSTER_SIZE = "w342";

export function posterUrl(path: string): string {
  return `${IMAGE_BASE}/${POSTER_SIZE}${path}`;
}

export function imageUrl(size: string, path: string): string {
  return `${IMAGE_BASE}/${size}${path}`;
}

export default function Poster({
  path,
  title,
  eager = false,
  className = "",
}: {
  path: string | null;
  title: string;
  eager?: boolean;
  className?: string;
}) {
  return (
    <div className={`aspect-[2/3] overflow-hidden rounded-lg bg-neutral-800 ${className}`}>
      {path && (
        <img
          src={posterUrl(path)}
          alt={title}
          loading={eager ? "eager" : "lazy"}
          className="h-full w-full object-cover"
        />
      )}
    </div>
  );
}
