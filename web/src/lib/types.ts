/**
 * TypeScript mirrors of the backend API DTOs (app/api/schemas/*).
 *
 * These match the Pydantic v2 response models exactly so the data-layer hooks
 * are fully typed. Enum unions mirror `app/db/models/common.py`.
 */

// ---- Enums ---------------------------------------------------------------

export type UserRole = "farmer" | "agronomist" | "coop_admin" | "super_admin";
export type Language = "en" | "sw";

export type DeviceType = "sensor_node" | "gateway" | "actuator";
export type DeviceStatus = "active" | "inactive" | "fault";

export type ActuatorType = "vent" | "fan" | "drip_valve" | "fertigation_pump";
export type ActuatorState = "open" | "closed" | "on" | "off" | "unknown";

export type RiskModelType =
  | "late_blight"
  | "tuta_absoluta"
  | "microclimate"
  | "nutrient"
  | "water";

export type RiskLevel = "none" | "low" | "medium" | "high" | "critical";

export type AlertStatus =
  | "pending"
  | "sent"
  | "delivered"
  | "failed"
  | "acked"
  | "escalated"
  | "suppressed";

export type CommandStatus = "queued" | "sent" | "acked" | "failed" | "expired";
export type CommandSource = "auto" | "manual";

export type PlanType = "subscription" | "rent_to_own" | "daas";
export type SubscriptionStatus =
  | "trial"
  | "active"
  | "past_due"
  | "suspended"
  | "cancelled";
export type PaymentStatus = "pending" | "success" | "failed" | "reversed";
export type PaymentProviderType = "mpesa" | "manual";

// ---- Auth + org ----------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: string;
  org_id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  preferred_language: Language;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_reseller: boolean;
  white_label: boolean;
  country: string;
  timezone: string;
  contact_email: string | null;
  contact_phone: string | null;
}

// ---- Farm hierarchy ------------------------------------------------------

export interface Farm {
  id: string;
  org_id: string;
  name: string;
  county: string | null;
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  area_ha: number | null;
}

export interface Greenhouse {
  id: string;
  org_id: string;
  farm_id: string;
  name: string;
  zone: string | null;
  structure_type: string | null;
  area_m2: number | null;
  install_date: string | null;
  notes: string | null;
}

export interface Device {
  id: string;
  org_id: string;
  greenhouse_id: string | null;
  device_uid: string;
  name: string;
  device_type: DeviceType;
  status: DeviceStatus;
  firmware_version: string | null;
  last_seen_at: string | null;
  last_battery_v: number | null;
  last_rssi: number | null;
  latitude: number | null;
  longitude: number | null;
}

// ---- Telemetry -----------------------------------------------------------

export interface Reading {
  device_id: string;
  time: string;
  greenhouse_id: string | null;
  air_temp_c: number | null;
  rh_pct: number | null;
  leaf_wetness: number | null;
  ppfd: number | null;
  co2_ppm: number | null;
  soil_moisture_pct: number | null;
  soil_temp_c: number | null;
  npk_n_ppm: number | null;
  npk_p_ppm: number | null;
  npk_k_ppm: number | null;
  water_flow_l_total: number | null;
  water_flow_l_per_min: number | null;
  pheromone_count: number | null;
  battery_v: number | null;
  rssi: number | null;
}

/** Telemetry value columns that `GET /readings?metric=` accepts. */
export type ReadingMetric =
  | "air_temp_c"
  | "rh_pct"
  | "leaf_wetness"
  | "ppfd"
  | "co2_ppm"
  | "soil_moisture_pct"
  | "soil_temp_c"
  | "npk_n_ppm"
  | "npk_p_ppm"
  | "npk_k_ppm"
  | "water_flow_l_total"
  | "water_flow_l_per_min"
  | "pheromone_count"
  | "battery_v"
  | "rssi";

// ---- Risk / alerts / recommendations -------------------------------------

export interface RiskAssessment {
  id: string;
  greenhouse_id: string;
  crop_cycle_id: string | null;
  model_type: RiskModelType;
  level: RiskLevel;
  score: number;
  window_start: string | null;
  window_end: string | null;
  details: Record<string, unknown>;
  evaluated_at: string;
}

export interface Alert {
  id: string;
  greenhouse_id: string;
  risk_assessment_id: string | null;
  model_type: RiskModelType;
  level: RiskLevel;
  title: string;
  dedup_key: string;
  status: AlertStatus;
  escalation_level: number;
  first_seen_at: string;
  last_sent_at: string | null;
  acked_at: string | null;
  acked_by: string | null;
}

export interface Recommendation {
  id: string;
  alert_id: string | null;
  risk_assessment_id: string | null;
  action_code: string;
  message_en: string;
  message_sw: string;
  priority: number;
  default_language: Language;
  overridden: boolean;
  override_message: string | null;
  override_by: string | null;
  override_at: string | null;
  farmer_accepted: boolean | null;
}

// ---- Control -------------------------------------------------------------

export interface Actuator {
  id: string;
  greenhouse_id: string;
  name: string;
  actuator_type: ActuatorType;
  state: ActuatorState;
  is_online: boolean;
  last_state_change: string | null;
}

export interface ControlCommand {
  id: string;
  actuator_device_id: string;
  automation_rule_id: string | null;
  command: string;
  params: Record<string, unknown>;
  status: CommandStatus;
  source: CommandSource;
  issued_by: string | null;
  issued_at: string;
  sent_at: string | null;
  acked_at: string | null;
  error: string | null;
}

export interface CommandIn {
  command: string;
  params?: Record<string, unknown> | null;
}

// ---- Billing -------------------------------------------------------------

export interface Subscription {
  id: string;
  plan_type: PlanType;
  plan_name: string;
  status: SubscriptionStatus;
  price: number;
  currency: string;
  billing_interval: string;
  features: Record<string, unknown>;
  trial_ends_at: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  started_at: string | null;
}

export interface SubscribeIn {
  plan_type?: PlanType;
  phone: string;
  amount: number;
  plan_name?: string;
}

export interface STKResult {
  ok: boolean;
  subscription_id: string;
  payment_id: string;
  checkout_request_id: string | null;
  merchant_request_id: string | null;
  customer_message: string | null;
  error: string | null;
}

export interface Payment {
  id: string;
  subscription_id: string | null;
  installment_id: string | null;
  provider: PaymentProviderType;
  amount: number;
  currency: string;
  status: PaymentStatus;
  phone: string | null;
  account_reference: string | null;
  merchant_request_id: string | null;
  checkout_request_id: string | null;
  mpesa_receipt: string | null;
  result_code: number | null;
  result_desc: string | null;
  initiated_at: string;
  completed_at: string | null;
}

// ---- Weather -------------------------------------------------------------

export interface WeatherObservation {
  id: string;
  farm_id: string;
  observed_at: string;
  source: string;
  air_temp_c: number | null;
  rh_pct: number | null;
  wind_speed_ms: number | null;
  rainfall_mm: number | null;
  clouds_pct: number | null;
}

export interface WeatherForecast {
  id: string;
  farm_id: string;
  issued_at: string;
  forecast_for: string;
  source: string;
  air_temp_c: number | null;
  rh_pct: number | null;
  rain_prob: number | null;
  rainfall_mm: number | null;
  wind_speed_ms: number | null;
}

export interface FarmWeather {
  farm_id: string;
  observation: WeatherObservation | null;
  forecasts: WeatherForecast[];
}
