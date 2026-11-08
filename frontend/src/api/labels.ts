import type { TasteCluster } from "./types";

/** Küme adı: elle veya LLM ile verilen isim, yoksa baskın türlerden üretilen başlık. */
export function clusterTitle(cluster: TasteCluster): string {
  return cluster.label ?? cluster.auto_title;
}
