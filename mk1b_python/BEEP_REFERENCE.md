# Altimeter Field Beep Reference

**Pyro 1 = Drogue** (fires at apogee, ~10 ft past peak)
**Pyro 2 = Main** (fires below 500 ft AGL on descent)

**Mode select (BEFORE power-on):**
- No jumper → **flight mode**
- Jumper installed (GP18 ↔ GP19) → **test mode**

---

## Flight Mode

### Boot sequence (plays once, in order)

| Sound | Meaning |
|---|---|
| Long beep (1 s) | Flight mode entry |
| 2 short beeps | Both pyros have continuity ✓ |
| 4 slow beeps | Pyro 1 (drogue) NO continuity — flies disarmed |
| 5 slow beeps | Pyro 2 (main) NO continuity — flies disarmed |
| Rapid 3 s chirp | Boot complete |

### On-pad indicator (sustained loop until launch — **CONFIRM BEFORE LAUNCH**)

| Sound (loops) | Status |
|---|---|
| Steady fast blip (4 Hz) | **READY** — both pyros armed |
| `blip-blip-blip-blip` … **4 BEEPS** | Pyro 1 disarmed — **NO drogue** |
| `blip-blip-blip-blip` … **5 BEEPS** | Pyro 2 disarmed — **NO main** |
| **4 BEEPS** … **5 BEEPS** (no blips) | Both disarmed — **DATA ONLY, NO DEPLOYMENT** |

If you don't hear the steady fast blip, your rocket will not perform a full dual-deploy. Confirm this is what you want before launch.

### Hard error (loops forever, blocks flight)

| Sound | Meaning |
|---|---|
| 3 slow beeps repeating | Baro sensor fail — power off, do not fly |

---

## Test Mode (jumper installed at boot)

| Step | Sound | Operator action |
|---|---|---|
| 1 | Long beep (1 s) | Test mode entered |
| 2 | 2 short / 4 slow / 5 slow | Note continuity status |
| 3 | Silent | **Remove** jumper to arm pyro 1 |
| 4 | Silent | **Re-install** jumper to commit |
| 5 | 5 ticks @ 1 Hz | Countdown — last chance |
| 6 | 0.3 s warning, then pyro 1 fires (1 s) | — |
| 7 | 3× beep-beep | Pyro 1 fired ✓ |
| 8–12 | Repeat steps 3–7 for pyro 2 | — |
| 13 | 1 short beep every 2 s | Test complete — power off |

**⚠ Warning:** in test mode, the **remove + re-install** jumper sequence FIRES the corresponding pyro for 1 second. Do not connect live e-matches unless you intend to fire.

---

## Quick lookup

- **4 beeps** = pyro 1 / drogue / apogee channel
- **5 beeps** = pyro 2 / main / 500 ft channel
- **3 beeps** = baro sensor fail
- **Long beep** = mode entry / pre-fire warning
- **Rapid chirp (3 s)** = boot complete
- **Steady fast blip** = on pad, ready, both armed
- **Heartbeat (1 beep / 2 s)** = test complete
