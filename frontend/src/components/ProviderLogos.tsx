import type { WatchProvider } from "../api/types";
import { imageUrl } from "./Poster";

const LOGO_SIZE = "w92";
const MAX_LOGOS = 5;

/** Abonelik platformları önce gelir; aynı platform bir kez gösterilir. */
export default function ProviderLogos({ providers }: { providers: WatchProvider[] }) {
  const unique = new Map<number, WatchProvider>();
  [...providers]
    .sort((a, b) => Number(b.type === "flatrate") - Number(a.type === "flatrate"))
    .forEach((p) => {
      if (!unique.has(p.id)) unique.set(p.id, p);
    });
  const shown = [...unique.values()].filter((p) => p.logo_path).slice(0, MAX_LOGOS);
  if (shown.length === 0) return null;
  return (
    <div className="flex gap-1">
      {shown.map((p) => (
        <img
          key={p.id}
          src={imageUrl(LOGO_SIZE, p.logo_path!)}
          alt={p.name}
          title={p.name}
          loading="lazy"
          className="size-6 rounded"
        />
      ))}
    </div>
  );
}
