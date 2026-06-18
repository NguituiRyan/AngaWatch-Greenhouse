/** Top bar: mobile menu toggle, org name, current user, and logout. */

import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeProvider";
import { humanize } from "@/lib/format";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { user, logout } = useAuth();
  const { orgName } = useTheme();

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur">
      <button
        type="button"
        onClick={onMenu}
        className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
        aria-label="Open navigation"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
        </svg>
      </button>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-700">{orgName}</p>
      </div>

      {user ? (
        <div className="flex items-center gap-3">
          <div className="hidden text-right sm:block">
            <p className="text-sm font-medium text-slate-700">{user.full_name}</p>
            <p className="text-xs text-slate-400">{humanize(user.role)}</p>
          </div>
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/10 text-sm font-semibold text-brand">
            {user.full_name.charAt(0).toUpperCase()}
          </span>
          <button type="button" onClick={logout} className="btn-secondary px-3 py-1.5 text-xs">
            Sign out
          </button>
        </div>
      ) : null}
    </header>
  );
}
