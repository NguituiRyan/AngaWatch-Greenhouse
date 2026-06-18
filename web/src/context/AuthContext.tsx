/**
 * Authentication context.
 *
 * Holds the access/refresh token pair (persisted to localStorage so a refresh
 * keeps the session) and the current user. Login uses the OAuth2 password form
 * at `/auth/login`; `setTokenProvider` is wired so the api layer always reads
 * the live access token.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { api, ApiError, setTokenProvider } from "@/lib/api";
import type { TokenResponse, User } from "@/lib/types";

const ACCESS_KEY = "angawatch.access_token";
const REFRESH_KEY = "angawatch.refresh_token";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  /** True while we bootstrap the session (e.g. validating a stored token). */
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const accessRef = useRef<string | null>(localStorage.getItem(ACCESS_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // The api layer reads the current token through this provider.
  setTokenProvider(() => accessRef.current);

  const persistTokens = useCallback((tokens: TokenResponse | null) => {
    if (tokens) {
      accessRef.current = tokens.access_token;
      localStorage.setItem(ACCESS_KEY, tokens.access_token);
      localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
    } else {
      accessRef.current = null;
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
    }
  }, []);

  const logout = useCallback(() => {
    persistTokens(null);
    setUser(null);
  }, [persistTokens]);

  const loadUser = useCallback(async () => {
    try {
      const me = await api.get<User>("/auth/me");
      setUser(me);
    } catch (err) {
      // Stored token invalid/expired — drop the session.
      if (err instanceof ApiError && err.status === 401) {
        persistTokens(null);
      }
      setUser(null);
    }
  }, [persistTokens]);

  const login = useCallback(
    async (email: string, password: string) => {
      const form = new URLSearchParams();
      form.set("username", email);
      form.set("password", password);
      const tokens = await api.loginForm<TokenResponse>("/auth/login", form);
      persistTokens(tokens);
      await loadUser();
    },
    [persistTokens, loadUser],
  );

  // Bootstrap: if a token is already stored, validate it by loading the user.
  useEffect(() => {
    let active = true;
    (async () => {
      if (accessRef.current) {
        await loadUser();
      }
      if (active) setIsLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [loadUser]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isLoading,
      login,
      logout,
    }),
    [user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
