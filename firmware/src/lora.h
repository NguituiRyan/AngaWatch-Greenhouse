// ============================================================================
// lora.h — SX1276/RFM95 LoRa transport for the AngaWatch node
// ----------------------------------------------------------------------------
// Thin wrapper over sandeepmistry/LoRa. The node sends one JSON telemetry packet
// per wake to the field gateway, which validates it against TelemetryIn and
// republishes to MQTT topic farm/{org_id}/{device_id}/telemetry. Raw LoRa (not
// LoRaWAN) keeps the demo gateway simple; swap in RadioHead/LMIC for LoRaWAN.
// ============================================================================

#ifndef ANGAWATCH_LORA_H
#define ANGAWATCH_LORA_H

#include <Arduino.h>

namespace lora {

// Initialize SPI + radio with the parameters in config.h. Returns false if the
// SX1276 does not respond (bad wiring / wrong pins) so the caller can still sleep
// instead of busy-looping. Safe to call once per wake.
bool begin();

// Transmit a UTF-8 JSON payload as a single LoRa packet (blocking until the TX
// done IRQ). Returns false if the radio was never initialized.
bool sendPacket(const String &json);

// Last packet RSSI (dBm) observed by the radio, for the telemetry "rssi" field.
// This is the node's view of the most recent RX; on a TX-only node it reflects
// the ambient noise floor and is mostly informational.
int32_t lastRssi();

// Put the radio into its lowest-power sleep state before MCU deep sleep.
void sleep();

}  // namespace lora

#endif  // ANGAWATCH_LORA_H
