/**
 * White-label theming.
 *
 * Reads the caller's organization (`GET /organizations/me`) and, when the org is
 * white-labelled with a `theme.primary` colour, applies it to the `--brand` CSS
 * variable so Tailwind's `brand` colour follows the reseller's branding. The
 * org name + a derived initials mark are exposed for the topbar/sidebar.
 *
 * `theme` is not part of OrganizationOut, so theming degrades gracefully to the
 * AngaWatch default when absent.
 */

import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";

import { useOrganization } from "@/hooks/useOrganization";
import { useAuth } from "./AuthContext";

interface ThemeState {
  orgName: string;
  brandLabel: string;
  whiteLabel: boolean;
}

const ThemeContext = createContext<ThemeState>({
  orgName: "AngaWatch",
  brandLabel: "AngaWatch",
  whiteLabel: false,
});

/** Convert "#16a34a" -> "22 163 74" for the `rgb(var(--brand))` syntax. */
function hexToRgbTriplet(hex: string): string | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const int = parseInt(m[1], 16);
  return `${(int >> 16) & 255} ${(int >> 8) & 255} ${int & 255}`;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const { data: org } = useOrganization(isAuthenticated);

  // `theme` may ride along on the org payload even though the typed DTO omits it.
  const theme = (org as { theme?: { primary?: string } } | undefined)?.theme;

  useEffect(() => {
    const root = document.documentElement;
    const primary = theme?.primary;
    if (org?.white_label && primary) {
      const triplet = hexToRgbTriplet(primary);
      if (triplet) root.style.setProperty("--brand", triplet);
    } else {
      root.style.removeProperty("--brand");
    }
    return () => {
      root.style.removeProperty("--brand");
    };
  }, [org?.white_label, theme?.primary]);

  const value = useMemo<ThemeState>(() => {
    const orgName = org?.name ?? "AngaWatch";
    return {
      orgName,
      brandLabel: org?.white_label ? orgName : "AngaWatch",
      whiteLabel: Boolean(org?.white_label),
    };
  }, [org?.name, org?.white_label]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  return useContext(ThemeContext);
}
