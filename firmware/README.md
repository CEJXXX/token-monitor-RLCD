# firmware

ESP-IDF v5.x project for the Waveshare ESP32-S3-RLCD-4.2. Polls the bridge
daemon every `RLCD_POLL_SEC` seconds, renders a monospace terminal dashboard
on the 400×300 reflective LCD via LVGL v9.

## Layout

```
firmware/
├── CMakeLists.txt
├── partitions.csv
├── sdkconfig.defaults
├── main/
│   ├── CMakeLists.txt
│   ├── main.cpp              # entry; wires display + lvgl + UserApp_*
│   ├── user_config.h         # RLCD pins / resolution (from vendor demo)
│   ├── idf_component.yml     # lvgl/lvgl ^9.4.0
│   └── secrets.h.example     # → copy to secrets.h (gitignored)
└── components/
    ├── port_bsp/             # RLCD panel driver (verbatim from vendor 09_LVGL_V9_Test)
    ├── app_bsp/              # LVGL port: double-buffer in PSRAM + tick + lock (verbatim from vendor)
    ├── net_app/              # WiFi STA (blocking connect helper)
    ├── usage_client/         # esp_http_client + cJSON parse → usage_report_t
    ├── ui_app/               # our LVGL terminal-style dashboard
    └── user_app/             # glue: wifi init, ui init, polling task
```

`port_bsp/` and `app_bsp/` are an unmodified copy of the vendor demo at
`ESP32-S3-RLCD-4.2-Demo/02_ESP-IDF/09_LVGL_V9_Test/components/`. Don't
edit them — pull a refresh from the vendor zip if upstream changes.

## Build & flash

```bash
cd firmware
cp main/secrets.h.example main/secrets.h
$EDITOR main/secrets.h           # fill in WiFi + bridge URL + token

idf.py set-target esp32s3
idf.py build flash monitor
```

The first `idf.py build` will fetch `lvgl/lvgl@^9.4.0` via the IDF component
manager.

### Windows quick start

There is only one ESP-IDF distribution; "GUI" vs "CLI" is just *how* you
invoke the same `idf.py`. Install once, pick whichever frontend you like.

1. **Install the toolchain (once, ~3 GB):**
   download the **Universal Online Installer** from
   <https://dl.espressif.com/dl/esp-idf/> and pick the latest v5.x.
   - Let it install its bundled Python + Git (don't reuse system ones).
   - Target chip: `esp32s3`.
   - The installer drops `ESP-IDF 5.x PowerShell` / `ESP-IDF 5.x CMD`
     shortcuts in the Start menu — these are CMD/PowerShell windows with
     all the env vars pre-set.

2. **Clone the repo to a short, ASCII-only path** — e.g. `C:\dev\RLCD`.
   Spaces or CJK in the path will break the IDF toolchain.

3. **Pick a frontend:**

   | Frontend | When | How |
   | --- | --- | --- |
   | **VSCode + Espressif IDF extension** (recommended) | day-to-day dev, autocomplete, debugger | install VSCode → install the "Espressif IDF" extension → Command Palette → `ESP-IDF: Configure ESP-IDF Extension` → point at the IDF you just installed → open the `firmware/` folder, use the status-bar buttons for build / flash / monitor |
   | **ESP-IDF PowerShell** | one-off builds, scripting | Start menu → `ESP-IDF 5.x PowerShell` → `cd C:\dev\RLCD\firmware` → commands below |

4. **First build & flash** (works the same in either frontend):
   ```powershell
   cd C:\dev\RLCD\firmware
   copy main\secrets.h.example main\secrets.h
   notepad main\secrets.h          # fill in WiFi / bridge URL / token
   idf.py set-target esp32s3
   idf.py build flash monitor
   ```
   Plug the board's USB-C in first. If the COM port isn't detected,
   install the CH343 / USB-JTAG driver from the Waveshare wiki.
   `Ctrl+]` exits the serial monitor.

5. **Gotchas:**
   - Add the ESP-IDF install dir to Windows Defender exclusions — otherwise
     real-time scanning slows compiles by 5-10×.
   - First build downloads `lvgl/lvgl@^9.4.0` via the IDF component manager
     (~50 MB) — needs internet.
   - If build complains about line endings in the vendor BSP files, run
     `git config --global core.autocrlf input` and re-clone.

## What to expect

- Boot:
  - serial prints `connecting to <ssid>...` → `got IP ...`
  - LVGL initialises, screen shows `claude-code @ rlcd ~ $ status` +
    `waiting for bridge...`
- Within `RLCD_POLL_SEC` seconds the dashboard fills with real numbers.
- If the bridge becomes unreachable: header shows `(stale)`, numbers freeze.

## Verification

1. **Mock data**: set `RLCD_BRIDGE_URL` to `http://<bridge>/api/usage?mock=1`,
   flash, confirm UI shape matches `docs/ui-mockup.txt`.
2. **Live data**: switch to no query string, run Claude Code on the bridge
   host for a minute, watch the 5h tokens count up on the next poll.
3. **Resilience**: stop the bridge service — UI should mark stale and
   keep the last good numbers, no crash.

## Hardware reference (from vendor `user_config.h`)

```
RLCD: 400 × 300, monochrome via RGB565→threshold in flush callback
SPI3 — MOSI=12, SCK=11, DC=5, CS=40, RST=41 (TE=6)
I2C  — SDA=13, SCL=14  (used by onboard PCF85063 RTC and SHTC3, unused here)
```
