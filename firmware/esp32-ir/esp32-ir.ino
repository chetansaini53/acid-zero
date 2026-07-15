/*
 * Acid Zero - IR co-processor firmware (STANDALONE, on a SECOND ESP32)
 * -------------------------------------------------------------------
 * Keeps the working CC1101 ESP32 completely UNTOUCHED. This runs on its own
 * ESP32, plugged into the Pi over USB serial. Both ESP32s share /dev/ttyUSB*,
 * so the two are told apart WITHOUT changing the Sub-GHz client:
 *   - the CC1101 firmware answers PING with "PONG"  -> the Sub-GHz client keeps it
 *   - THIS firmware answers PING with "IR_READY"    -> Sub-GHz client SKIPS it
 *   - the IR client (acid_ir.py) probes with IR_INFO -> finds THIS one
 *
 * Wiring (IR modules -> this ESP32):
 *   IR Transmitter  S/DAT -> GPIO13   VCC -> 3.3V   GND -> GND
 *   IR Receiver     OUT   -> GPIO14   VCC -> 3.3V   GND -> GND
 *
 * REQUIRES:  IRremoteESP8266 >= 2.8.6   (arduino-cli lib install IRremoteESP8266)
 * Serial protocol (one command/line, 115200):
 *   PING            -> IR_READY  (deliberately NOT "PONG")
 *   IR_INFO         -> pins + lib
 *   IR_RX [sec]     -> capture one press -> IR_PROTO + IR_RAW <freq> <us...> + IR_END
 *   IR_TX_RAW <freq> <reps> <us...> -> transmit a raw pulse train -> IR_OK
 *
 * Educational / own-lab use only. IR_TX_RAW emits IR - own devices / authorized only.
 */
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>

static const uint16_t PIN_IR_TX = 13;   // IR LED driver
static const uint16_t PIN_IR_RX = 14;   // TSOP/VS1838 demod OUT
static const uint16_t IR_BUF = 1024;    // long enough for AC frames

IRsend g_irsend(PIN_IR_TX);
IRrecv g_irrecv(PIN_IR_RX, IR_BUF, 15 /*ms end-gap*/, true);
decode_results g_irres;

static void doIrRx(int secs) {
  if (secs < 1) secs = 8;
  if (secs > 20) secs = 20;
  Serial.printf("IR_RX start %ds - point remote + press a button\n", secs);
  g_irrecv.enableIRIn();
  uint32_t end = millis() + (uint32_t)secs * 1000UL;
  while (millis() < end) {
    if (g_irrecv.decode(&g_irres)) {
      String pn = typeToString(g_irres.decode_type, false);
      Serial.printf("IR_PROTO name=%s addr=%X cmd=%X bits=%u\n",
                    pn.c_str(), (unsigned)g_irres.address,
                    (unsigned)g_irres.command, g_irres.bits);
      uint16_t len = getCorrectedRawLength(&g_irres);
      uint16_t *raw = resultToRawArray(&g_irres);
      Serial.print("IR_RAW 38000");
      for (uint16_t i = 0; i < len; i++) Serial.printf(" %u", raw[i]);
      Serial.println();
      delete[] raw;
      g_irrecv.resume();
      Serial.println("IR_END");
      return;
    }
    delay(4);
  }
  Serial.println("IR_TIMEOUT");
  Serial.println("IR_END");
}

static void doIrTxRaw(const String &args) {
  static uint16_t buf[IR_BUF];
  int n = 0, field = 0, idx = 0, L = args.length();
  long freq = 38000, reps = 1;
  while (idx < L) {
    while (idx < L && args[idx] == ' ') idx++;
    int j = idx;
    while (j < L && args[j] != ' ') j++;
    if (j > idx) {
      long v = args.substring(idx, j).toInt();
      if (field == 0) freq = v;
      else if (field == 1) reps = v;
      else if (n < IR_BUF) buf[n++] = (uint16_t)v;
      field++;
    }
    idx = j;
  }
  if (n < 2) { Serial.println("IR_ERR no data"); return; }
  if (reps < 1) reps = 1;
  if (reps > 10) reps = 10;
  uint16_t khz = (freq >= 30000 && freq <= 60000) ? (uint16_t)(freq / 1000) : 38;
  for (int r = 0; r < reps; r++) { g_irsend.sendRaw(buf, n, khz); delay(20); }
  Serial.printf("IR_OK sent=%d reps=%ld @%ukHz\n", n, reps, khz);
  g_irrecv.enableIRIn();   // re-arm RX after TX
}

static void handle(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  String up = cmd; up.toUpperCase();
  if (up == "PING") {
    Serial.println("IR_READY");            // NOT "PONG" - so the Sub-GHz client skips us
  } else if (up == "IR_INFO") {
    Serial.printf("IR_INFO tx=%u rx=%u lib=IRremoteESP8266 buf=%u\n",
                  PIN_IR_TX, PIN_IR_RX, IR_BUF);
  } else if (up.startsWith("IR_RX")) {
    doIrRx(cmd.substring(5).toInt());
  } else if (up.startsWith("IR_TX_RAW")) {
    doIrTxRaw(cmd.substring(9));
  } else {
    Serial.println("ERR unknown. cmds: PING IR_INFO IR_RX IR_TX_RAW");
  }
}

void setup() {
  Serial.setRxBufferSize(8192);   // big IR_TX_RAW lines (full raw frames from the Pi)
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== Acid Zero IR co-processor (standalone ESP32) ===");
  g_irsend.begin();
  g_irrecv.enableIRIn();
  Serial.println("IR ready: RX=GPIO14 TX=GPIO13 (IRremoteESP8266). cmds: PING IR_INFO IR_RX IR_TX_RAW");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    handle(line);
  }
}
