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
| **Robust DCT ID** | 128-bit watermark + registry lookup | JPEG, resize, mild blur (σ≤1), moderate edits |
| **Geo sync** | SIFT homography + TPS/flow morph re-align | Rotation, paste, swirl, occlusion |
| **Auto-match** | pHash shortlist → SIFT over registry refs | Sub-image in another picture |
| **LSB** | Full message (AES-GCM + RS + copies) | Lossless PNG/BMP only — **not** resize/crop |
| **Visible** | Diagonal stamp + FFT verify | Human-readable ownership cue |

On extraction the engine walks layers in recovery order: LSB (lossless) → robust
ID → blind deskew → auto-match (homography, then morph TPS+flow).

**A message only ever comes from bits actually present in the image.** If the
watermark is destroyed, extraction fails closed and returns nothing. It never
falls back to "this looks like a picture I have on file" — see
[Known limits](#known-limits).

### Keys

A key is **mandatory**; there is no default. Watermark keys are password-derived
and **portable**: a decoder only ever has the password, so an image embedded on
one machine opens on another. Two derivations, deliberately different:

| Secret | Derivation | Why |
| ------ | ---------- | --- |
| Content key (AES-GCM) | Argon2id + **fresh 16-byte salt per message**, salt stored in the payload | Where confidentiality lives; same password never yields the same key twice |
| Permutation seed | Argon2id + fixed protocol constant | Cannot be salted — you would need the permutation to read the salt |
| Registry key (local) | Random material + **user+machine fingerprint** | Never leaves the machine, so a stolen key file alone does not decrypt it |

### Known limits

The invisible robust ID uses **mid-frequency DCT + JND QIM** with per-block
adaptive strength: flat areas are skipped, mildly-textured blocks get a floored
scale so their step stays stable, and texture ramps up from there. The QIM step
is derived only from quantities the embedder never modifies, so encoder and
blind decoder agree on the lattice. Embedding self-verifies: it escalates
strength until the mark reads back **and** survives JPEG q50, and raises rather
than shipping an image whose watermark cannot be read.

It survives JPEG, resize, crop, and **mild Gaussian blur (σ≈1)**. Strong defocus
(**σ≥2**) destroys it — low-frequency embedding was measured and rejected
(visible 8×8 grid on sky/skin), and SyncSeal/WAM do not restore frequency
content after blur. In that case extraction reports failure; it does not guess.

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

## Security

- **Mandatory key** — no default, no silent fallback
- **Argon2id** key derivation, **per-message random salt** for the content key
- **AES-GCM** for LSB payload and encrypted registry at rest
- **User+machine binding** for local at-rest secrets
- **SHA-256-pinned** AI model artifacts, repo fetched at a pinned commit
- **API key** optional auth for registry and mutation endpoints
- No similarity-based attribution: an unwatermarked image is never matched

## Optional AI sync / localize (CPU)

Off by default. Requires PyTorch (CPU wheel is enough; ~32 GB RAM is fine).
Models download on first use into `~/.stashpix/models/` (~480 MB total) and are
**not** bundled in the portable zip / MSI.

```bash
pip install -e ".[ai]"
# or CPU torch explicitly:
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

stashpix embed -i cover.png -o out.png -m "secret" -k pass --syncseal --wam
stashpix extract -i out.png -k pass --try-syncseal --try-wam --show-info
```

- **SyncSeal** — blind geometric re-alignment before robust DCT extract.
- **WAM** — localize watermarked ROI + 32-bit fingerprint shortlist; the full
  message still comes from the robust 128-bit ID + registry.
- Overrides: `STASHPIX_SYNCSEAL`, `STASHPIX_WAM`, `STASHPIX_WAM_ROOT`.
- Third-party weights/code: Meta SyncSeal / Watermark Anything (MIT WAM weights);
  see their upstream licenses.

**Integrity.** These checkpoints are deserialized by `torch.load` and the WAM
repo is imported from `sys.path` — both run code. Every artifact is SHA-256
pinned and verified before use (including paths given via the env overrides),
and the repo is fetched at a pinned commit rather than a moving branch. A
mismatch is a hard failure, not a "model unavailable" downgrade. Deliberate
overrides need `STASHPIX_ALLOW_UNPINNED_MODELS=1`.

## Bundled app

```powershell
packaging\build.ps1 -Version 1.5.0   # -> dist/stashpix/ + packaging/out/stashpix-1.5.0.msi
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
