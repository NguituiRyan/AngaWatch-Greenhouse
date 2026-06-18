/** 404 fallback. */

import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <p className="text-5xl font-bold text-slate-300">404</p>
      <p className="mt-2 text-lg font-semibold text-slate-700">Page not found</p>
      <Link to="/" className="btn-primary mt-6 px-4 py-2">
        Back to dashboard
      </Link>
    </div>
  );
}
