# App icons

Drop real icon assets here to have them embedded in the packaged builds. The
spec files reference them by name and fall back to the default PyInstaller icon
if a file is absent, so builds still succeed without them.

| File       | Platform | Format                          |
|------------|----------|---------------------------------|
| `app.ico`  | Windows  | `.ico` (multi-resolution)       |
| `app.icns` | macOS    | `.icns`                         |
| `app.png`  | Linux    | `.png` (256×256 recommended)    |

These are intentionally not committed as binaries — generate them from a single
source PNG (e.g. with ImageMagick / `iconutil` / online converters) as needed.
