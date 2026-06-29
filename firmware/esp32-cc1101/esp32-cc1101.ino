/*
 * Acid Zero - Sub-GHz Co-Processor firmware (CC1101 on ESP32-WROOM-32)
 * -------------------------------------------------------------------
 * The ESP32 owns the CC1101 over its own clean VSPI (no display to fight),
 * and talks to the Raspberry Pi over USB serial (115200). The Pi launcher
 * sends short text commands; this firmware drives the radio and replies.
 *
 * Wiring (CC1101 -> ESP32 board label):
 *   GND -> GND   VCC -> 3V3   GDO0 -> D4
 *   CSN -> D5    SCK -> D18   MOSI -> D19   MISO -> D23   GDO2 -> (NC)
 *   NOTE: MOSI=D19 / MISO=D23 (brute-force confirmed by the pin constants below).
 *   Crossing these two is the classic "VER reads 0x00" failure - match it exactly.
 *
 * Library: SmartRC-CC1101-Driver-Lib (ELECHOUSE)  -- install via:
 *   arduino-cli lib install "SmartRC-CC1101-Driver-Lib"
 *   Board (FQBN): esp32:esp32:esp32   (full flashing steps: ../README.md)
 *
 * Serial protocol (one command per line, 115200 baud):
 *   PING            -> PONG  (the Pi uses this to auto-detect the serial port)
 *   VER             -> chip PARTNUM/VERSION + present flag (the "is it alive" test)
 *   INFO            -> pin map + current freq + modulation profile
 *   FREQ <mhz>      -> set frequency (e.g. FREQ 433.92)
 *   RSSI            -> one RSSI reading (dBm) at current freq
 *   SCAN            -> RSSI sweep across 315/433.92/868/915 MHz
 *   ANALYZE         -> peak-hold sweep of the common sub-GHz list -> strongest freq
 *   WATCH <sec>     -> stream RSSI at current freq for <sec> seconds (signal hunt)
 *   MOD <profile>   -> switch modulation: AM_DEFAULT|AM_WIDE|AM_NARROW|FM_FSK
 *   SET_CONFIG ...  -> custom override: --freq --mod --drate --dev --rxbw --rssi
 *   CLASSIFY        -> hold a remote 3s -> guess ASK/OOK (AM) vs 2-FSK (FM)
 *   CAPTURE [sec]   -> RMT raw-OOK capture (full timing) -> CAP n + CAPDATA <us...>
 *   LOAD <us...>    -> load a saved signal (sent from the Pi) into the TX buffer
 *   REPLAY [reps]   -> transmit the loaded/captured signal
 *
 * Educational / authorized-lab use only. REPLAY transmits RF - use ONLY on your
 * own devices / authorized test gear, on a frequency that is legal in your region.
 */

#include <ELECHOUSE_CC1101_SRC_DRV.h>

// ---- pin map (ESP32 board labels D5/D18/D23/D19/D4 = GPIO 5/18/23/19/4) ----
static const uint8_t PIN_SCK  = 18;
static const uint8_t PIN_MISO = 23;   // CC1101 MISO/SO  (brute-force confirmed: SO is on D23)
static const uint8_t PIN_MOSI = 19;   // CC1101 MOSI/SI  (brute-force confirmed: SI is on D19)
static const uint8_t PIN_CS   = 5;
static const uint8_t PIN_GDO0 = 4;

static float    g_freq = 433.92f;   // MHz
static bool     g_ok   = false;     // CC1101 detected this boot

static void ccApplyPins() {
  ELECHOUSE_cc1101.setSpiPin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS);
  ELECHOUSE_cc1101.setGDO0(PIN_GDO0);
}

// getCC1101() reads PARTNUM/VERSION and returns true only on a valid chip id.
static bool ccPresent() { return ELECHOUSE_cc1101.getCC1101(); }

// ---- CC1101 modulation PROFILES (Flipper-style: AM = ASK/OOK, FM = 2-FSK) ----
typedef struct { uint8_t mod; float rxbw; float drate; float dev; const char* name; } Profile;
static const Profile PROFILES[] = {
  {2, 162.0f, 2.4f, 0.0f,  "AM_DEFAULT"},  // 0: proven clean OOK baseline
  {2, 650.0f, 4.0f, 0.0f,  "AM_WIDE"},     // 1: OOK wide 650 kHz (AM650 style)
  {2, 270.0f, 3.8f, 0.0f,  "AM_NARROW"},   // 2: OOK narrow 270 kHz (AM270 remotes)
  {0, 270.0f, 5.0f, 47.6f, "FM_FSK"},      // 3: 2-FSK, 47.6 kHz deviation (FM476)
};
static const int N_PROFILES = 4;
static int     g_profile = 0;
static uint8_t g_mod   = 2;
static float   g_rxbw  = 162.0f, g_drate = 2.4f, g_dev = 0.0f;
static int     g_rssi_th = -75;           // carrier-sense threshold

static int profileByName(const String &s) {
  for (int i = 0; i < N_PROFILES; i++)
    if (s.equalsIgnoreCase(PROFILES[i].name)) return i;
  return -1;
}
static void loadProfile(int p) {
  if (p < 0 || p >= N_PROFILES) return;
  g_profile = p;
  g_mod = PROFILES[p].mod; g_rxbw = PROFILES[p].rxbw;
  g_drate = PROFILES[p].drate; g_dev = PROFILES[p].dev;
}

// Apply the current (profile or custom) config. Name kept = ookConfig so all
// existing callers (ccBringUp / asyncOff / doCapture / playPulses) stay valid.
static void ookConfig() {
  ELECHOUSE_cc1101.setModulation(g_mod);   // 2=ASK/OOK(AM), 0=2-FSK(FM)
  ELECHOUSE_cc1101.setMHZ(g_freq);
  ELECHOUSE_cc1101.setDRate(g_drate);
  ELECHOUSE_cc1101.setRxBW(g_rxbw);
  if (g_mod != 2) ELECHOUSE_cc1101.setDeviation(g_dev > 0 ? g_dev : 47.6f);
  ELECHOUSE_cc1101.setPA(12);
}

static void ccBringUp() {
  // Init() runs SPI.begin() with custom pins (+ reset + config). getCC1101()
  // does NOT init SPI, so it must be called AFTER Init() or it reads 0x00.
  ELECHOUSE_cc1101.Init();
  g_ok = ccPresent();
  if (g_ok) { ookConfig(); ELECHOUSE_cc1101.SetRx(); }
}

// MOD <name|index>: switch modulation profile.
static void doMod(String arg) {
  arg.trim();
  int p = profileByName(arg);
  if (p < 0) { int idx = arg.toInt(); if (idx >= 0 && idx < N_PROFILES) p = idx; }
  if (p < 0) { Serial.println("MOD ERR - AM_DEFAULT|AM_WIDE|AM_NARROW|FM_FSK"); return; }
  loadProfile(p); ookConfig();
  Serial.printf("MOD %s (mod=%d rxbw=%.0f drate=%.2f dev=%.1f)\n",
                PROFILES[g_profile].name, g_mod, g_rxbw, g_drate, g_dev);
}

// SET_CONFIG --freq X --mod NAME --drate D --dev V --rxbw B --rssi R  (custom override)
static void doSetConfig(const String &args) {
  String tok[24]; int nt = 0, i = 0, L = args.length();
  while (i < L && nt < 24) {
    while (i < L && args[i] == ' ') i++;
    int j = i; while (j < L && args[j] != ' ') j++;
    if (j > i) tok[nt++] = args.substring(i, j);
    i = j;
  }
  for (int k = 0; k + 1 < nt; k++) {
    String key = tok[k], val = tok[k + 1];
    if (key == "--freq") g_freq = val.toFloat();
    else if (key == "--mod") { int p = profileByName(val); if (p >= 0) loadProfile(p); else g_mod = (uint8_t)val.toInt(); }
    else if (key == "--drate") g_drate = val.toFloat();
    else if (key == "--dev") g_dev = val.toFloat();
    else if (key == "--rxbw") g_rxbw = val.toFloat();
    else if (key == "--rssi") g_rssi_th = val.toInt();
  }
  ookConfig();
  Serial.printf("CONFIG freq=%.2f mod=%d rxbw=%.0f drate=%.2f dev=%.1f rssi_th=%d prof=%s\n",
                g_freq, g_mod, g_rxbw, g_drate, g_dev, g_rssi_th, PROFILES[g_profile].name);
}

// CLASSIFY: sample RSSI for 3s while the remote is held -> guess AM(OOK) vs FM(FSK).
// AM keys the carrier on/off (big RSSI swing); FM keeps carrier on (small swing).
static void doClassify() {
  if (!g_ok) { Serial.println("CLASSIFY ERR - CC1101 not present"); return; }
  Serial.println("CLASSIFY - hold the remote for 3s...");
  ookConfig();
  ELECHOUSE_cc1101.SetRx();
  int rmin = 999, rmax = -999;
  uint32_t end = millis() + 3000;
  while (millis() < end) {
    int r = ELECHOUSE_cc1101.getRssi();
    if (r < rmin) rmin = r;
    if (r > rmax) rmax = r;
    delay(4);
  }
  int span = rmax - rmin;
  const char* guess;
  if (span >= 15)            guess = "ASK/OOK (AM) -> use AM_NARROW or AM_WIDE";
  else if (rmax > -70)       guess = "constant carrier -> likely FSK (FM), try MOD FM_FSK";
  else                       guess = "weak/no signal - hold closer or run ANALYZE";
  Serial.printf("CLASSIFY rssi_min=%d max=%d span=%d -> %s\n", rmin, rmax, span, guess);
}

static void printVer() {
  bool ok = ccPresent();
  uint8_t part = ELECHOUSE_cc1101.SpiReadStatus(0x30); // PARTNUM (expect 0x00)
  uint8_t ver  = ELECHOUSE_cc1101.SpiReadStatus(0x31); // VERSION (expect 0x14/0x04)
  Serial.printf("VER partnum=0x%02X version=0x%02X present=%s\n",
                part, ver, ok ? "YES" : "NO");
  if (!ok) Serial.println("HINT: 0x00/0xFF + present=NO => check 3.3V power and the 4 SPI wires.");
}

static int readRssiOnce() {
  ELECHOUSE_cc1101.SetRx();
  delay(15);
  return ELECHOUSE_cc1101.getRssi();   // dBm
}

// Peak-hold: poll RSSI for `ms` and keep the max. Needed to catch bursty OOK
// remotes (a single snapshot usually lands in the inter-packet gap).
static int readRssiPeak(int ms) {
  ELECHOUSE_cc1101.SetRx();
  delay(3);
  int best = -200;
  uint32_t end = millis() + (uint32_t)ms;
  while (millis() < end) {
    int r = ELECHOUSE_cc1101.getRssi();
    if (r > best) best = r;
  }
  return best;
}

static void doScan() {
  const float freqs[] = {315.0f, 433.92f, 868.0f, 915.0f};
  Serial.println("SCAN start");
  for (uint8_t i = 0; i < 4; i++) {
    ELECHOUSE_cc1101.setMHZ(freqs[i]);
    int r = readRssiOnce();
    Serial.printf("SCAN %.2f MHz  rssi=%d dBm\n", freqs[i], r);
  }
  ELECHOUSE_cc1101.setMHZ(g_freq);   // restore
  Serial.println("SCAN done");
}

static void doAnalyze() {
  // Sweep the common sub-GHz frequencies (Flipper-style hopper list) and
  // report the one with the strongest RSSI -> "find the remote's frequency".
  static const float fl[] = {300.00f, 303.87f, 304.25f, 310.00f, 315.00f, 318.00f,
                             390.00f, 418.00f, 433.07f, 433.42f, 433.92f, 434.42f,
                             434.78f, 438.90f, 868.35f, 915.00f};
  const int N = sizeof(fl) / sizeof(fl[0]);
  Serial.println("ANALYZE start");
  float bestF = 0; int bestR = -200;
  for (int i = 0; i < N; i++) {
    ELECHOUSE_cc1101.setMHZ(fl[i]);
    int r = readRssiPeak(120);   // peak-hold to catch bursty OOK remotes
    Serial.printf("ANALYZE %.2f rssi=%d\n", fl[i], r);
    if (r > bestR) { bestR = r; bestF = fl[i]; }
  }
  ELECHOUSE_cc1101.setMHZ(g_freq);   // restore
  Serial.printf("ANALYZE peak=%.2f rssi=%d\n", bestF, bestR);
}

static void doWatch(int secs) {
  if (secs < 1) secs = 5;
  if (secs > 60) secs = 60;
  ELECHOUSE_cc1101.setMHZ(g_freq);
  Serial.printf("WATCH %.2f MHz for %d s (press your 433 remote near the antenna)\n", g_freq, secs);
  uint32_t end = millis() + (uint32_t)secs * 1000UL;
  while (millis() < end) {
    int r = readRssiOnce();
    // crude bar so a signal is obvious on a plain serial monitor
    int bars = (r + 110) / 6; if (bars < 0) bars = 0; if (bars > 20) bars = 20;
    Serial.printf("WATCH rssi=%4d dBm ", r);
    for (int b = 0; b < bars; b++) Serial.print('#');
    Serial.println();
    delay(120);
  }
  Serial.println("WATCH done");
}

// ============ OOK RAW capture / replay (Flipper "Read RAW + Send") ============
// RX uses the ESP32 RMT peripheral = hardware-precise edge timing -> consistent
// pulse counts (like Flipper), unlike GPIO interrupts which merge/drop fast edges.
#define CAP_MAX 600
uint16_t _capBuf[CAP_MAX];
int _capN = 0;
static rmt_data_t _rmt[256];   // 256 symbols = up to 512 captured pulses

static void asyncOn() {
  ELECHOUSE_cc1101.SpiWriteReg(0x08, 0x30);  // PKTCTRL0 = async serial mode (raw OOK on GDO0)
  ELECHOUSE_cc1101.SpiWriteReg(0x02, 0x0D);  // IOCFG0   = async serial data I/O on GDO0
}
static void asyncOff() {
  ELECHOUSE_cc1101.Init();                    // restore lib packet/FIFO defaults
  ookConfig();
  ELECHOUSE_cc1101.SetRx();
}

static void doCapture(int secs) {
  if (!g_ok) { Serial.println("CAPTURE ERR - CC1101 not present"); return; }
  if (secs < 1) secs = 6; if (secs > 20) secs = 20;
  Serial.printf("CAPTURE start %.2f MHz %ds - send/hold the signal now\n", g_freq, secs);
  _capN = 0;
  ookConfig();
  asyncOn();
  ELECHOUSE_cc1101.SetRx();
  // RMT RX on GDO0 @ 1us tick = hardware-precise edge capture (no merge/drop)
  if (!rmtInit(PIN_GDO0, RMT_RX_MODE, RMT_MEM_NUM_BLOCKS_4, 1000000)) {
    asyncOff();
    Serial.println("CAP n=0");
    Serial.println("CAPTURE ERR - rmtInit failed");
    return;
  }
  size_t nsym = 256;
  rmtRead(PIN_GDO0, _rmt, &nsym, (uint32_t)secs * 1000UL);
  rmtDeinit(PIN_GDO0);
  asyncOff();
  // Keep the FULL raw (incl inter-frame gaps so repeats replay faithfully).
  // Start at the first carrier-ON (level==1) pulse so replay (which starts HIGH)
  // stays phase-aligned; skip the leading idle.
  bool started = false;
  for (size_t i = 0; i < nsym && _capN < CAP_MAX; i++) {
    uint16_t d0 = _rmt[i].duration0, d1 = _rmt[i].duration1;
    uint8_t  l0 = _rmt[i].level0,    l1 = _rmt[i].level1;
    if (!started) {
      if (l0 == 1 && d0 > 50) {
        started = true;
      } else if (l1 == 1 && d1 > 50 && d1 < 32000) {
        _capBuf[_capN++] = d1; started = true; continue;
      } else {
        continue;
      }
    }
    if (d0 > 50 && d0 < 32000) _capBuf[_capN++] = d0;
    if (_capN < CAP_MAX && d1 > 50 && d1 < 32000) _capBuf[_capN++] = d1;
  }
  Serial.printf("CAP n=%d\n", _capN);
  Serial.print("CAPDATA");
  for (int i = 0; i < _capN; i++) Serial.printf(" %u", _capBuf[i]);
  Serial.println();
  Serial.println(_capN >= 16 ? "CAPTURE ok" : "CAPTURE empty/weak - hold closer, retry");
}

static void playPulses(int reps) {
  if (reps < 1) reps = 5; if (reps > 30) reps = 30;
  ookConfig();
  asyncOn();
  pinMode(PIN_GDO0, OUTPUT);
  digitalWrite(PIN_GDO0, LOW);
  ELECHOUSE_cc1101.SetTx();
  delay(2);
  for (int r = 0; r < reps; r++) {
    int level = HIGH;                       // 1st captured duration is a carrier-on pulse
    for (int i = 0; i < _capN; i++) {
      digitalWrite(PIN_GDO0, level);
      delayMicroseconds(_capBuf[i]);
      level = !level;
    }
    digitalWrite(PIN_GDO0, LOW);
    delay(10);                              // inter-frame gap
  }
  asyncOff();
}

static void doReplay(int reps) {
  if (!g_ok) { Serial.println("REPLAY ERR - CC1101 not present"); return; }
  if (_capN < 8) { Serial.println("REPLAY ERR - nothing captured (run CAPTURE)"); return; }
  Serial.printf("REPLAY %d pulses x%d @ %.2f MHz\n", _capN, reps < 1 ? 5 : reps, g_freq);
  playPulses(reps);
  Serial.println("REPLAY done");
}

// LOAD <d1> <d2> ... : store a signal sent from the Pi (saved file) for REPLAY.
static void doLoad(const String &args) {
  int n = 0, idx = 0, len = args.length();
  while (idx < len && n < CAP_MAX) {
    while (idx < len && args[idx] == ' ') idx++;
    int j = idx;
    while (j < len && args[j] != ' ') j++;
    if (j > idx) { _capBuf[n++] = (uint16_t)args.substring(idx, j).toInt(); idx = j; }
    else break;
  }
  _capN = n;
  Serial.printf("LOAD n=%d\n", _capN);
}

static void handle(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  String up = cmd; up.toUpperCase();

  if (up == "PING") {
    Serial.println("PONG");
  } else if (up == "VER") {
    printVer();
  } else if (up == "INFO") {
    Serial.printf("INFO pins SCK=%u MISO=%u MOSI=%u CS=%u GDO0=%u | freq=%.2f | prof=%s mod=%d rxbw=%.0f drate=%.2f dev=%.1f | present=%s\n",
                  PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS, PIN_GDO0, g_freq, PROFILES[g_profile].name, g_mod, g_rxbw, g_drate, g_dev, g_ok ? "YES" : "NO");
  } else if (up.startsWith("FREQ")) {
    float f = cmd.substring(4).toFloat();
    if (f >= 280.0f && f <= 950.0f) {
      g_freq = f;
      ELECHOUSE_cc1101.setMHZ(g_freq);
      Serial.printf("FREQ set %.2f MHz\n", g_freq);
    } else {
      Serial.println("FREQ ERR (use 280-950, e.g. FREQ 433.92)");
    }
  } else if (up == "RSSI") {
    Serial.printf("RSSI %.2f MHz = %d dBm\n", g_freq, readRssiOnce());
  } else if (up == "SCAN") {
    doScan();
  } else if (up == "ANALYZE") {
    doAnalyze();
  } else if (up.startsWith("WATCH")) {
    doWatch(cmd.substring(5).toInt());
  } else if (up.startsWith("CAPTURE")) {
    doCapture(cmd.substring(7).toInt());
  } else if (up.startsWith("REPLAY")) {
    doReplay(cmd.substring(6).toInt());
  } else if (up.startsWith("LOAD")) {
    doLoad(cmd.substring(4));
  } else if (up.startsWith("SET_CONFIG") || up.startsWith("SETCFG")) {
    int sp = cmd.indexOf(' ');
    doSetConfig(sp >= 0 ? cmd.substring(sp + 1) : "");
  } else if (up.startsWith("MOD")) {
    doMod(cmd.substring(3));
  } else if (up == "CLASSIFY") {
    doClassify();
  } else {
    Serial.println("ERR unknown. cmds: PING VER INFO FREQ RSSI SCAN ANALYZE WATCH CAPTURE REPLAY LOAD MOD SET_CONFIG CLASSIFY");
  }
}

void setup() {
  Serial.setRxBufferSize(4096);   // big LOAD lines (full raw signals from the Pi)
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== Acid Zero Sub-GHz co-processor (CC1101 on ESP32) ===");
  ccApplyPins();
  ccBringUp();
  if (g_ok) Serial.println("CC1101 DETECTED + initialised (ASK/OOK @ 433.92 MHz).");
  else      Serial.println("CC1101 NOT detected - check 3.3V power + the 4 SPI wires.");
  printVer();
  Serial.println("cmds: PING VER INFO FREQ RSSI SCAN ANALYZE WATCH CAPTURE REPLAY LOAD | MOD <prof> SET_CONFIG --k v CLASSIFY");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    handle(line);
  }
}
