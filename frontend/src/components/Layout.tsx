import { NavLink, Outlet } from "react-router";
import { useProgress } from "../hooks/useLibrary";

const LINKS = [
  { to: "/", label: "Öner" },
  { to: "/puanla", label: "Puanla" },
  { to: "/zevkim", label: "Zevkim" },
  { to: "/listem", label: "Listem" },
  { to: "/ara", label: "Ara" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm transition-colors ${
    isActive ? "font-semibold text-white" : "text-neutral-400 hover:text-white"
  }`;

export default function Layout() {
  const { data } = useProgress();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-neutral-800 bg-neutral-950">
        <div className="mx-auto flex max-w-[1296px] flex-wrap items-center gap-x-6 gap-y-2 px-8 py-3.5">
          <NavLink to="/" className="font-display text-lg font-bold text-white">
            Gece Seansı
          </NavLink>
          <nav className="flex flex-wrap gap-5" aria-label="Ana menü">
            {LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.to === "/"} className={linkClass}>
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4">
            {data && (
              <span className="text-[13px] text-neutral-400">
                {data.rated} / {data.target} puan
              </span>
            )}
            <NavLink to="/ayarlar" className={linkClass}>
              Ayarlar
            </NavLink>
          </div>
        </div>
      </header>
      <div className="flex flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}
