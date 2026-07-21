# Stashpix

**Your ID, stashed in the pixels.**

Robust image identification and ownership recovery for photos — embed a durable
128-bit ID that survives JPEG, resize, crop, morph, and partial occlusion, then
look up the full message from a local registry. Optional LSB carries the complete
payload on lossless images; visible watermarking adds human-readable proof.

Positioned like Digimarc-style **image ID / leak tracing**, but local-first:
CLI, desktop GUI, and REST API. Fully internationalized (English + Hungarian).

## What it does

| Layer | Role | Survives |
| ----- | ---- | -------- |
| **Robust DCT ID** | 128-bit watermark + registry lookup | JPEG, resize, moderate edits |
| **Geo sync** | SIFT homography + TPS/flow morph re-align | Rotation, paste, swirl, occlusion |
| **Auto-match** | pHash shortlist → SIFT over registry refs | Sub-image in another picture |
| **LSB** | Full message (AES-GCM + RS + copies) | Lossless PNG/BMP only — **not** resize/crop |
| **Visible** | Diagonal stamp + FFT verify | Human-readable ownership cue |

On extraction the engine walks layers in recovery order: LSB (lossless) → robust
ID → blind deskew → auto-match (homography, then morph TPS+flow).

## Architecture

```
src/stashpix/
├── config.py            # EmbedConfig / ExtractConfig / VerifyConfig
├── engine.py            # StegoEngine — pipeline + graceful degradation
├── core/                # crypto (AEAD), keys (Argon2id), perceptual hash, DCT
├── layers/              # LSB, robust DCT, geometry, visible watermark
├── registry/            # Encrypted JSON store + pHash index
├── cli.py               # unified `stashpix` CLI
├── gui/app.py           # Tkinter GUI
└── api/                 # FastAPI + static dashboard (optional API key auth)
```

## Install

```bash
pip install -e .                 # core (+ argon2, cryptography)
pip install -e ".[geo]"          # + opencv-contrib-python (SIFT + TPS)
pip install -e ".[api]"          # + FastAPI/uvicorn
pip install -e ".[dev]"          # + pytest
```

## CLI

```bash
stashpix --lang en embed -i cover.png -o out.png -m "secret" -k pass \
      --copies 3 --visible-text "(c) Me 2026"
stashpix extract -i out.png -k pass
stashpix verify-visible -i out.png -t "(c) Me 2026" -k pass
stashpix extract-geo -i composite.png -r out.png -k pass   # needs [geo]
stashpix gui
stashpix serve --host 127.0.0.1 --port 8000                # needs [api]
```

`--lang en|hu` or `STASHPIX_LANG`. Legacy `~/.stego` migrates to `~/.stashpix` on first run.

## Python API

```python
from stashpix import StegoEngine, EmbedConfig, ExtractConfig, VerifyConfig

engine = StegoEngine()
engine.embed_file("cover.png", "secret", "out.png",
                  EmbedConfig(key="pass", lsb_copies=3, visible_text="(c) Me"))
message, info = engine.extract_file("out.png", ExtractConfig(key="pass"))
```

## REST API

Start `stashpix serve`. Set `STASHPIX_API_KEY` to require `Authorization: Bearer <key>`
or `X-API-Key` on sensitive endpoints (`/api/registry`, embed/extract/stats).

- `GET  /` — web UI
- `GET  /api/health`, `GET /api/stats`, `GET /api/registry`, `GET /api/i18n`
- `POST /api/embed`, `/api/extract`, `/api/verify-visible`

## Data storage

| OS      | Location              |
| ------- | --------------------- |
| Windows | `%USERPROFILE%\.stashpix\` |
| Linux   | `$HOME/.stashpix/`    |
| macOS   | `$HOME/.stashpix/`    |

Contents: encrypted `registry.json`, `stashpix_refs/` (reference images + pHash),
`.registry_key` (local encryption key). Overrides: `STASHPIX_HOME`, `STASHPIX_REGISTRY`,
`STASHPIX_REGISTRY_KEY`.

## Security (1.3.0+)

- **Argon2id** key derivation (replaces SHA-256 + `random.Random`)
- **AES-GCM** for LSB payload and encrypted registry at rest
- **API key** optional auth for registry and mutation endpoints

## Bundled app

```powershell
packaging\build.ps1 -Version 1.3.0   # -> dist/stashpix/ + packaging/out/stashpix-1.3.0.msi
```

## Tests

```bash
pytest
python scripts/cli_stress_test.py
```

## License

PolyForm Noncommercial License 1.0.0 — see [LICENSE](LICENSE).  
**Author:** Rózsavölgyi János — [@arlinamid](https://github.com/arlinamid/stashpix)

Acceptance recorded under `~/.stashpix/eula_accepted.json` (`STASHPIX_ACCEPT_LICENSE=1` for CI).

---

### Magyar összefoglaló

Robosztus képazonosító és tulajdon-visszakeresés: DCT ID + titkosított registry +
geometriai szinkron (homográfia, morph TPS+flow) + opcionális LSB és látható vízjel.
CLI: `stashpix`, adat: `~/.stashpix`. Nyelv: `STASHPIX_LANG=hu`.
