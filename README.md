# stegosuite

Multi-layer steganography suite combining four independent layers with **graceful
degradation**, exposed through a unified **CLI**, a desktop **GUI**, and a REST
**API** (SaaS backend). Fully **internationalized** (English + Hungarian).

## Layers

1. **LSB** (`layers/lsb.py`) — Reed-Solomon + key-based spreading + XOR-whitening
   + redundant copies. Carries the **full message**; survives crop/repaint, not
   JPEG/resize.
2. **Robust DCT watermark** (`layers/robust.py`) — a 128-bit ID embedded in
   mid-frequency DCT coefficients with perceptually adaptive QIM (Watson JND).
   Survives JPEG/resize; the message is stored in a **registry** keyed by the ID.
3. **Geometric synchronizer** (`layers/geometry.py`) — three modes (optional,
   needs OpenCV):
   - *Auto-match (registry as image index)*: at embed time a downscaled reference
     copy of the stego is stored in the registry; plain `extract` (no reference
     flag) then SIFT-matches a suspect against **every** stored reference and
     self-recovers — even from a rotated / occluded **sub-image** dropped into
     another picture. This solves "recognize a piece of our image in the wild".
   - *Reference-based* (`extract-geo`): SIFT + homography re-align to a reference
     you pass explicitly. Handles arbitrary rotation, scaling, sub-image paste and
     partial occlusion.
   - *Reference-free (blind)*: background-colour segmentation + deskew +
     orientation probe. Recovers images reframed / letterboxed / cropped onto a
     **solid background** (0/90/180/270°). Arbitrary fine rotation with no
     reference/registry match is not recoverable (DCT-QIM needs sub-pixel grid
     alignment).
4. **Visible watermark** (`layers/visible.py`) — a human-readable diagonal stamp
   plus blind, translation-invariant verification.

On extraction the engine walks the layers in order of recovery strength: LSB first
(full message), then robust ID → registry, then blind deskew, then auto-match
against the registry's reference index.

## Architecture

```
src/stegosuite/
├── config.py            # EmbedConfig / ExtractConfig / VerifyConfig + defaults
├── exceptions.py        # translatable exception hierarchy
├── engine.py            # StegoEngine — pipeline + graceful degradation
├── i18n/                # Translator + en/hu message catalogs
├── core/                # imaging, coding (Hamming/RS/bits), dct/JND, Layer ABC
├── layers/              # LsbLayer, RobustWatermarkLayer, VisibleWatermarkLayer, GeometricSynchronizer
├── registry/            # Registry (JSON store, swappable)
├── cli.py               # unified `stego` CLI
├── gui/app.py           # Tkinter GUI (live language switch)
└── api/                 # FastAPI backend + static dashboard
```

## Install

```bash
pip install -e .                 # core (numpy, Pillow, reedsolo)
pip install -e ".[geo]"          # + OpenCV (geometric sync)
pip install -e ".[api]"          # + FastAPI/uvicorn (REST API)
pip install -e ".[dev]"          # + pytest
```

## CLI

```bash
stego --lang en embed -i cover.png -o stego.png -m "secret" -k pass \
      --copies 3 --visible-text "(c) Me 2026"
stego extract -i stego.png -k pass
stego verify-visible -i stego.png -t "(c) Me 2026" -k pass
stego extract-geo -i composite.png -r stego.png -k pass   # needs [geo]
stego gui                                                  # desktop app
stego serve --host 127.0.0.1 --port 8000                  # REST API + dashboard, needs [api]
```

`--lang en|hu` selects the interface language (default: `hu`, or the
`STEGOSUITE_LANG` environment variable).

## Python API

```python
from stegosuite import StegoEngine, EmbedConfig, ExtractConfig, VerifyConfig

engine = StegoEngine()
engine.embed_file("cover.png", "secret", "stego.png",
                  EmbedConfig(key="pass", lsb_copies=3, visible_text="(c) Me"))
message, info = engine.extract_file("stego.png", ExtractConfig(key="pass"))
present, score, _ = engine.verify_visible_file(
    "stego.png", VerifyConfig(text="(c) Me", key="pass"))
```

## REST API

Start `stego serve`, then:

- `GET  /` — interactive web UI (live state + embed/extract/verify tools)
- `GET  /research` — research infographic
- `GET  /api/health`, `GET /api/stats`, `GET /api/registry`, `GET /api/i18n`
- `POST /api/embed` — multipart `file`, `message`, `key`, `copies`, `visible_text` → stego PNG (`X-Robust-Id` header)
- `POST /api/extract` — multipart `file`, `key`, optional `reference` (a suspected
  original, for rotated/cropped/reframed images) → JSON `{ok, message, layer}`
- `POST /api/verify-visible` — multipart `file`, `text`, `key` → JSON `{present, score}`

The web UI and desktop GUI both expose the optional **reference image** on the
extract screen: if a user finds an image suspicious, they can supply the original
to re-align and verify it.

Add `?lang=en` (or `hu`) to localize responses.

## Data storage

The registry and the reference-image index are stored per-user, the same way on
every OS:

| OS      | Location                                   |
| ------- | ------------------------------------------ |
| Windows | `%USERPROFILE%\.stego\`                    |
| Linux   | `$HOME/.stego/`                            |
| macOS   | `$HOME/.stego/`                            |

Inside it: `registry.json` (ID → message) and `stego_refs/` (reference images for
auto-matching). Overrides: `STEGOSUITE_HOME` (the data dir) or
`STEGOSUITE_REGISTRY` (the exact registry file path).

## Bundled app & installer

A standalone bundle (no Python required) plus a Windows MSI installer live under
[`packaging/`](packaging/):

```powershell
# from a dev env with the package + extras installed
packaging\build.ps1            # -> dist/stego/  and  packaging/out/Stegosuite-1.1.0.msi
```

The bundle contains `stego.exe` (CLI) and `stego-gui.exe` (desktop app). The MSI
installs to *Program Files*, adds `stego` to the system `PATH`, and creates a
Start-menu shortcut for the GUI. See `packaging/README.md` for prerequisites
(PyInstaller, WiX Toolset v4+) and Linux/macOS bundling notes.

## Tests

```bash
pip install pytest
pytest
```

### End-to-end CLI stress test

Drives the real `stego` CLI as a subprocess against an isolated registry and
exercises every command plus attacks (JPEG, resize, crop, occlusion, SIFT
sub-image, wrong key, i18n, error paths). Critical cases affect the exit code;
robustness cases are reported best-effort.

```bash
python scripts/cli_stress_test.py          # add --keep to inspect artifacts
```

## License

Stegosuite is licensed under the **[PolyForm Noncommercial License 1.0.0](LICENSE)**.

- **Personal / noncommercial use — free.** Personal projects, research,
  education, hobby use, and use by noncommercial organizations are all permitted,
  including modifying and redistributing under the same terms.
- **Commercial use — approval required.** Any commercial use needs a separate
  commercial license, granted only with the author's prior written approval.
  To request one, contact the author (below).
- **Encoded Media clause.** Files produced by this software (images/audio/video
  carrying a watermark or hidden payload) may be created and shared for
  noncommercial purposes. **Commercial distribution** of such encoded media —
  for example, publication by an online newspaper, news agency, or any for-profit
  outlet — is a commercial use and **requires a commercial license.** See the
  *Additional Terms — Encoded Media* section in [`LICENSE`](LICENSE).

**Author:** Rózsavölgyi János — GitHub: [@arlinamid](https://github.com/arlinamid)

See [`LICENSE`](LICENSE) for the full text, and [`CHANGELOG.md`](CHANGELOG.md)
for the release history.

### License acceptance (first run)

On first use, the CLI, GUI and server ask you to accept the license terms once.
Acceptance is recorded per license version under `~/.stego/eula_accepted.json`.

```bash
stego license --status     # show acceptance status + summary
stego license --show       # print the full LICENSE
stego license --accept     # accept non-interactively
stego <cmd> --accept-license   # accept inline with any command
```

For CI/automation, set `STEGOSUITE_ACCEPT_LICENSE=1` to accept automatically.
The API exposes the status at `GET /api/license`.

---

### Magyar összefoglaló

Több rétegű szteganográfia (LSB + robusztus DCT-vízjel + geometriai szinkron +
látható vízjel) egységes **CLI**-vel, **GUI**-val és **REST API**-val, teljes
**angol/magyar i18n**-nel. A felület nyelve: `stego --lang hu …`, vagy a
`STEGOSUITE_LANG=hu` környezeti változó. Telepítés és használat a fenti angol
szakaszok szerint.

**Szerző:** Rózsavölgyi János — GitHub: [@arlinamid](https://github.com/arlinamid)

**Licenc:** PolyForm Noncommercial License 1.0.0 — a **személyes / nem
kereskedelmi** használat ingyenes (módosítás és továbbadás is), a **kereskedelmi**
használathoz külön licenc kell, amit a szerző csak **előzetes jóváhagyással** ad.
**Kódolt média záradék:** a szoftverrel készült, vízjelet vagy rejtett adatot
hordozó fájlok (kép/hang/videó) nem kereskedelmi célra szabadon készíthetők és
megoszthatók, de az ilyen kódolt média **kereskedelmi terjesztéséhez** (pl. egy
online újság vagy bármely profitorientált kiadó általi közzététel) **kereskedelmi
licenc szükséges** — lásd az *Additional Terms — Encoded Media* szakaszt a
[`LICENSE`](LICENSE) fájlban. Kereskedelmi engedélyért keresd a szerzőt a fenti
GitHub-profilon. Részletek:
[`LICENSE`](LICENSE).
