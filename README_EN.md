# Christmas Wonderland v2.0.0 — Pixel Christmas Desktop App

A Windows desktop application built with Python and PySide6. It runs independently and does not require the integrated launcher.

## Features

The settings dialog groups language, display visibility, performance, and backup controls under **General**. English labels that need more space wrap onto multiple lines instead of being clipped.

- **Main widget:** Transparent pixel-art widget with a clock, date, and D-Day counter; normal or always-bottom window mode; quick menu; saved position and size.
- **Desktop snow:** Pixel-block snowfall across all monitors. Snow accumulates on window tops, the taskbar, and the ground; it conserves mass and reacts to the cursor, wind, and gusts. Temperature reduces snow amount and height without producing meltwater.
- **Snowman workshop:** Roll snowballs to collect snow, assemble snowmen, and decorate them. User-built (dynamic) snowmen melt with temperature; decorative snowmen do not. State is saved and restored.
- **Snow globes:** Up to 12 isometric snow globes, each with independent physics, appearance, background, decorations, and snow settings. State is saved and restored.
- **Weather and automatic weather:** Manual controls and automatic weather with 12 variables, per-variable automatic/manual modes, ranges, five presets, and user presets. Manually changing a variable during automatic mode switches only that variable to manual.
- **Decorations, lights, and clocks:** Place and edit pixel decorations, manage light strings, and choose from six desktop clock themes.
- **Advent calendar:** Unlockable boxes for December 1–24, with quizzes, wishes, and catch events. JSON configuration can launch external `.py` or `.exe` programs for individual days without changing application code.
- **Audio:** Built-in and user-provided music (files or folders), repeat and volume controls, and five sound effects (snow, wind, blizzard, fireplace, and bells) linked to weather.
- **Tray and taskbar visibility:** Choose independently whether the system-tray icon and the main taskbar button are shown; at least one remains enabled. The tray menu also opens application windows and controls automatic weather.
- **General settings:** Language selection, tray/taskbar visibility, performance options, autosave, and backup management.

## Requirements

- Windows (Win32 integration and the packaged application are Windows-oriented)
- Python 3.10 or newer recommended
- PySide6 6.6 or newer

## Run from source

```powershell
python -m pip install -r requirements.txt
python main.py
```

If an error occurs, check `data/app.log`. The `data/` directory is created at runtime. If the application directory is not writable, the app falls back to `%APPDATA%\ChristmasWonderland\data`.

## Build a Windows executable

Run `build.bat` on Windows. PyInstaller creates:

```text
dist/ChristmasWonderland/ChristmasWonderland.exe
```

The script also copies the `gifts/` directory beside the executable. The `data/` directory is created at runtime.

## Repository layout

```text
main.py                 Application entry point
advent/                 Advent calendar and event logic
assets/                 Fonts, music, language files, images, and icon
audio/                  Music and sound-effect management
clockface/              Desktop clock rendering and window
core/                   Shared application services and version information
decor/                  Decorations, lights, and sprites
docs/                   Design rules and development notes
gifts/                  Optional external Advent gift programs
settings/               Settings defaults and persistence
snow/                   Desktop snow simulation, physics, and overlays
snowglobe/              Isometric snow-globe model and rendering
snowman/                Snowman model, physics, and UI
weather/                Weather model and automatic-weather presets
widget/                 Main widget and settings UI
tests/                  Automated tests
tools/                  Development and benchmark utilities
data/                   Runtime-generated user data (not committed)
```

## Runtime data

The application stores user-specific and generated files in `data/`, including settings, snow-globe state, Advent progress and editable Advent content, backups, logs, lock files, and generated sound effects. These files are intentionally excluded from the Git repository. The default Advent content is bundled in `assets/advent/contents.default.json`.

## Launching external Advent gifts

Add an optional `action` object to a day in `data/advent_contents.json`:

```json
"action": { "type": "python", "file": "gifts/christmas_tree/main.py" }
"action": { "type": "executable", "file": "gifts/christmas_tree/christmas_tree.exe" }
```

- Each day can point to a different program. Days without `action` keep their normal behavior.
- Paths are relative to the application directory and must remain inside `gifts/`. Absolute paths, `..`, unsupported types, and unsupported extensions are rejected.
- The program starts as a separate process; the application does not wait for it. Duplicate launches of the same gift are prevented while it is running.
- If the file is missing or Python cannot be found, the app displays a warning. Successful launches do not show a confirmation popup.
- See [gifts/README.md](gifts/README.md) for details.

## Desktop snow overlay behavior

- One transparent overlay window is created per monitor and placed just above the desktop background and behind other windows. Its Z-order is not checked every frame; it is re-applied after events such as foreground-window or display changes, plus an occasional safety check.
- A separate top overlay per monitor draws snow over always-on-top decoration windows, sized to the visible decoration area. The taskbar is handled by fitting the top edge and hiding decorations behind it rather than by window order.
- Window frames are tracked using `EnumWindows` and DWM extended frame bounds at approximately 12 Hz. Cloaked, minimized, and click-through windows are excluded.
- Snow on a window is clipped according to the Z-order of windows above it, including this application's own windows.
- Wind can be adjusted from the settings tab, a separate wind-control window, the widget menu, or the tray menu.
- Snow on a monitor pauses when a fullscreen application covers that monitor. This behavior can be disabled in General settings.
- Environments where drawing is unavailable (such as the UAC secure desktop) are handled without terminating the application. The snow engine stops after the same drawing error occurs eight consecutive times.

## Tests

Run the logic and UI test modules individually from the project root:

```powershell
python -m unittest tests.test_core tests.test_snow tests.test_advent tests.test_autoweather tests.test_general_settings -v
python -m unittest tests.test_snow_physics tests.test_snow_v140 tests.test_snow_windows_stage2 tests.test_pile_restore tests.test_snowman -v
python -m unittest tests.test_stage3_ui tests.test_stage4_ui tests.test_stage5_ui tests.test_stage7_ui -v
python -m unittest tests.test_stage_a tests.test_stage_b tests.test_stage_c tests.test_stage_d tests.test_v195_stage2 tests.test_v200 -v
python -m unittest tests.test_i18n tests.test_i18n_table tests.test_logviewer tests.test_snowglobe_opt tests.test_snowglobe_v200_features -v
python -m unittest tests.test_v200_zorder tests.test_v200_snow_layers tests.test_v200_menu_floor -v
python -m unittest tests.test_frame_diag tests.test_lag_diag tests.test_minimize_release -v
python -m unittest tests.test_top_overlay_fit -v
```

Run `tests.test_top_overlay_fit` in its own command: without PySide6 it registers fake Qt modules that would interfere with other tests.

GUI tests that require PySide6:

```powershell
python -m unittest tests.test_gui_smoke tests.test_snowman_qt tests.test_step1_extras -v
```

`tests.test_stage6_ui` is intentionally omitted from the release test commands. The remaining UI checks run Stage 3–5 and Stage 7. The `tests/` directory has no `__init__.py`, so run tests by module name as shown instead of using `unittest discover`.

A GUI test that cannot run because PySide6 is unavailable is reported as skipped; it is not counted as a pass. Windows behavior, multi-monitor layouts and scaling, tray menus, audio playback, Win32 integration, fullscreen handling, and window/taskbar snow accumulation should be verified on a real Windows system.

## Known limitations

- GUI behavior, audio playback, and Win32 integration are not fully validated by automated tests. Verify multiple monitors and mixed display scaling, always-bottom mode, taskbar snow accumulation, fullscreen applications, music, and sound effects on Windows.
- Clear and cloudy weather are represented by snow amount only; screen colors are not changed. Automatic weather does not toggle the blizzard or gust switches.
- When adding music files, a file already present in a folder playlist may still be counted as "added" even though it is not duplicated in the list.
- External gift launching (`advent/launcher.py`) has automated logic tests for path validation, Python discovery, and asynchronous launch. Actual `.exe` launching, Python discovery, packaged `gifts/` paths, and button behavior require Windows testing. Console-only Python programs do not show a window; connect GUI programs instead. Microsoft Store `WindowsApps\python.exe` aliases are excluded from automatic discovery. Install the python.org distribution or use the `executable` action type if only the Store version is installed.

## Version history

See [README.md](README.md) for the full Korean changelog and detailed version history. The current application version is **v2.0.0** (`core/version.py`).

## License

This project is distributed under the [MIT License](LICENSE).
