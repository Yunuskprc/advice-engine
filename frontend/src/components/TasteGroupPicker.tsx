import { useState } from "react";
import type { TasteGroupChoice } from "../api/types";

export default function TasteGroupPicker({
  groups,
  saving,
  onSave,
  onCancel,
}: {
  groups: TasteGroupChoice[];
  saving: boolean;
  onSave: (groupIds: string[]) => void;
  onCancel?: () => void;
}) {
  const [selected, setSelected] = useState(
    () => new Set(groups.filter((g) => g.selected).map((g) => g.id)),
  );

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <div className="flex flex-1 flex-col">
      <main className="mx-auto w-full max-w-[1120px] flex-1 px-8 pt-14 pb-8">
        <h1 className="font-display text-[40px] leading-tight font-bold">
          Hangi filmler sana göre?
        </h1>
        <p className="mt-2.5 mb-7 max-w-[620px] text-neutral-400">
          İstediğin kadar grup seç. Bu sadece bir başlangıç, puan verdikçe zevkine göre genişler.
        </p>

        <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-3.5">
          {groups.map((g) => {
            const active = selected.has(g.id);
            return (
              <button
                key={g.id}
                type="button"
                aria-pressed={active}
                onClick={() => toggle(g.id)}
                className={`flex min-h-[172px] flex-col gap-2.5 rounded-[14px] border-2 p-4 text-left transition-colors ${
                  active
                    ? "border-amber-400 bg-[#2a2415]"
                    : "border-neutral-800 bg-neutral-900 hover:border-neutral-600"
                }`}
              >
                <span className="font-display text-[19px] font-bold">{g.name}</span>
                <span className="text-sm leading-relaxed text-neutral-300">{g.films}</span>
                <span className="mt-auto text-xs text-neutral-400">{g.tags}</span>
              </button>
            );
          })}
        </div>
      </main>

      <footer className="sticky bottom-0 border-t border-neutral-800 bg-neutral-900 px-8 py-3">
        <div className="mx-auto flex max-w-[1056px] flex-wrap items-center gap-x-5 gap-y-3">
          <p className="text-sm text-neutral-400">
            {selected.size > 0
              ? `${selected.size} grup seçildi`
              : "Devam etmek için en az bir grup seç"}
          </p>
          <div className="ml-auto flex gap-2">
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="h-11 rounded-[10px] border border-neutral-700 px-4 hover:bg-neutral-800"
              >
                Vazgeç
              </button>
            )}
            <button
              type="button"
              disabled={selected.size === 0 || saving}
              onClick={() => onSave([...selected])}
              className="h-11 rounded-[10px] bg-amber-400 px-7 font-semibold text-neutral-950 hover:bg-amber-300 disabled:opacity-50"
            >
              Filmleri göster
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
