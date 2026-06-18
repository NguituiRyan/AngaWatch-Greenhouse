/** Org hook: the caller's organization (drives white-label theming). */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Organization } from "@/lib/types";

export function useOrganization(enabled = true) {
  return useQuery({
    queryKey: ["organization", "me"],
    queryFn: () => api.get<Organization>("/organizations/me"),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}
