# tea: Ubuntu 24.04 notes

## 1. System packages

```bash
sudo apt install python3.12-venv libxcb-cursor0 libnotify-bin
```

- `python3.12-venv` for virtual environments.
- `libxcb-cursor0`: Qt 6.5 and later needs it for the X11 (xcb) platform plugin. Without it the app can fail to start under X11 with an error about the xcb plugin.
- `libnotify-bin` provides `notify-send`, useful for manual testing of notifications. The app itself talks to the notification service over DBus.

Install the app for daily use with `pipx` (`sudo apt install pipx`, then `pipx install .` in the repo) so it lives outside the system Python.

## 2. Wayland and X11

Ubuntu 24.04 uses GNOME on Wayland by default.

- **Window placement:** on Wayland, applications cannot choose where their windows appear. The question popup's bottom-right placement will be a request the compositor may ignore. This is expected. Do not add workarounds.
- **Always on top:** `Qt.WindowStaysOnTopHint` is advisory on GNOME Wayland. The popup may appear behind the active window. Accept this and rely on the notification as a prompt for important events.
- **Focus stealing:** GNOME restricts it. A popup shown without activation will not interrupt typing, which is the intended behavior for login prompts.
- **Dragging frameless windows:** use `QWindow.startSystemMove()`, which works on both Wayland and X11.
- **Clipboard:** Qt's clipboard works on Wayland while the app has focus or is running. If rich text paste fails on a given setup, record it in `docs/DEVIATIONS.md`.

## 3. Tray icon

Ubuntu's default session ships the AppIndicator extension, which lets Qt's `QSystemTrayIcon` show up. On a modified install without it, no icon appears. The app must still work: the window opens from the launcher, a second launch focuses the running instance, and `tea doctor` reports "tray not available".

## 4. Notifications

Use the `org.freedesktop.Notifications` DBus interface with an action list. GNOME supports a default action (clicking the notification). If calling DBus fails, fall back to `QSystemTrayIcon.showMessage` and log a warning.

## 5. Autostart

`tea install-autostart` writes `~/.config/autostart/tea-autostart.desktop` (from `desktop/tea-autostart.desktop`) and `~/.local/share/applications/tea.desktop`. The autostart entry runs `tea --background` with an 8 second delay so the session, tray and notification service are ready.

## 6. Fonts

Bundled fonts are loaded from `assets/fonts/` at startup. `tea doctor` prints which family Qt actually resolved for UI and reading text. System fallbacks (Noto Sans, Noto Serif) ship with Ubuntu.

## 7. Reduce motion

Read the desktop animation setting with:

```bash
gsettings get org.gnome.desktop.interface enable-animations
```

`false` means reduce motion. Use it as the default for the in-app setting.

## 8. Sleep and resume

The scheduler detects a resume by a wall-clock jump greater than 5 minutes between ticks, and also listens for `org.freedesktop.login1.Manager` `PrepareForSleep(false)` on the system bus when available.

## 9. Data locations

| What | Where |
|---|---|
| Database and uploads | `~/.local/share/tea/` |
| Settings | `~/.config/tea/settings.json` |
| Log | `~/.local/state/tea/tea.log` |
