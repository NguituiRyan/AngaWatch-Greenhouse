/** Billing hooks: subscription, payments, and STK-push subscribe. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Payment, STKResult, SubscribeIn, Subscription } from "@/lib/types";

/** The org's current subscription (may be null if never subscribed). */
export function useSubscription() {
  return useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: () => api.get<Subscription | null>("/billing/subscription"),
  });
}

export function usePayments() {
  return useQuery({
    queryKey: ["billing", "payments"],
    queryFn: () => api.get<Payment[]>("/billing/payments"),
  });
}

/** Fire an M-Pesa STK push for a subscription; refresh sub + payments after. */
export function useSubscribe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SubscribeIn) => api.post<STKResult>("/billing/subscribe", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["billing"] });
    },
  });
}
