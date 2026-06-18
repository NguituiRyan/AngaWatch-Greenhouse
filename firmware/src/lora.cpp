// ============================================================================
// lora.cpp — SX1276/RFM95 LoRa transport implementation
// ----------------------------------------------------------------------------
// Uses sandeepmistry/LoRa for raw LoRa packets. Configured from config.h:
// frequency 868 MHz, SF, bandwidth, coding rate, sync word and TX power. Each
// telemetry document goes out as a single packet; the gateway reassembles
// nothing because payloads are kept under the LoRa max (~255 B) by sending
// compact JSON.
// ============================================================================

#include "lora.h"
#include "config.h"

#include <SPI.h>
#include <LoRa.h>

namespace {
bool g_initialized = false;
}

namespace lora {

bool begin() {
  if (g_initialized) return true;

  // Map the SX1276 onto the board's SPI bus + control pins.
  SPI.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_SS);
  LoRa.setPins(PIN_LORA_SS, PIN_LORA_RST, PIN_LORA_DIO0);

  if (!LoRa.begin(static_cast<long>(LORA_FREQUENCY))) {
    // No reply from the radio — almost always wrong NSS/RST/DIO0 pins.
    g_initialized = false;
    return false;
  }

  // Radio link parameters. These MUST match the gateway's receiver config or the
  // gateway will hear nothing.
  LoRa.setTxPower(LORA_TX_POWER_DBM);
  LoRa.setSpreadingFactor(LORA_SPREADING);
  LoRa.setSignalBandwidth(static_cast<long>(LORA_BANDWIDTH));
  LoRa.setCodingRate4(LORA_CODING_RATE);
  LoRa.setSyncWord(LORA_SYNC_WORD);
  LoRa.setPreambleLength(LORA_PREAMBLE_LEN);
  LoRa.enableCrc();  // drop corrupted packets at the gateway

  g_initialized = true;
  return true;
}

bool sendPacket(const String &json) {
  if (!g_initialized) return false;
  LoRa.beginPacket();
  LoRa.print(json);
  // endPacket(false) = blocking until TX complete; returns 1 on success.
  const int ok = LoRa.endPacket();
  return ok == 1;
}

int32_t lastRssi() {
  return static_cast<int32_t>(LoRa.packetRssi());
}

void sleep() {
  if (g_initialized) {
    LoRa.sleep();   // SX1276 sleep mode (~0.2 µA)
  }
  SPI.end();
  g_initialized = false;
}

}  // namespace lora
