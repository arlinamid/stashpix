# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-07-22

### Added
- **Optional SyncSeal + WAM (CPU-first AI helpers, off by default):**
  - SyncSeal TorchScript geometric sync watermark (`--syncseal` / `--try-syncseal`).
  - WAM localization + 32-bit fingerprint shortlist (`--wam` / `--try-wam`); full
    message still comes from the robust 128-bit DCT ID + registry.
  - Lazy download into `~/.stashpix/models/` (overrides: `STASHPIX_SYNCSEAL`,
    `STASHPIX_WAM`, `STASHPIX_WAM_ROOT`). WAM code shallow-cloned to
    `~/.stashpix/vendor/watermark-anything` on first use.
  - Extras: `pip install -e ".[sync]"`, `".[wam]"`, or `".[ai]"` (torch CPU wheel
    recommended). Portable/MSI stays without model weights.
  - GUI toggles on Encode / Decode tabs (default off).
- **Registry fingerprint fallback (edge + pHash + dHash, not in-image):** when
  robust DCT decode fails (e.g. blur σ=2), extract matches the query against
  reference fingerprints stored at embed time. Strict pass (≤18 bit Hamming);
  **relaxed pass (≤64 bit, min gap 8)** for full-frame stylized edits (sketch /
  edge filter). Partial crops stay above 64 bit and are not matched.

### Fixed
- **Robust DCT frame had CRC detection only — one flipped bit meant total
  failure** even with a near-perfect SIFT alignment (e.g. 30%-crop pasted into
  another photo). The 160-bit `sync+id+crc` payload is now wrapped in
  **Hamming(7,4)** (`FRAME_BITS` 160 → 280 on the wire) so single-bit errors
  per group are corrected before the CRC check. Defaults stay **invisible**:
  mid-frequency `COEFS_MID` + adaptive `jnd` (strength 3).
- **Per-block adaptive JND (default on):** embed strength scales with 8×8 AC
  energy — flat sky/gradients are skipped entirely; textured blocks ramp to full
  strength by `TEXTURE_FULL=64`. Extract uses the same blind scale so decode
  stays aligned. Config: `robust_auto_adapt` (default `True`).
- **Fingerprint fallback respects embed key:** registry `key_tag` prevents
  edge-match recovery when the extract password does not match the embed key.

### Known limits
- **Gaussian blur σ=2 (`blur2`)** is beyond the invisible mid-band DCT ID. Mild
  blur (σ=1, `blur1`) is supported; stronger defocus destroys mid-frequency QIM
  parity. Low-frequency QIM (e.g. fixed Q≈55) was measured and rejected — visible
  8×8 grid on flat areas (~30 dB PSNR). Not a product target.

## [1.3.0] - 2026-07-21

### Changed
- **Rebrand to Stashpix** — package `stashpix`, CLI `stashpix` / `stashpix-gui`,
  data dir `~/.stashpix` (auto-migrates from `~/.stego`).
- **Security hardening:** Argon2id key derivation, AES-GCM for LSB payloads,
  encrypted registry at rest, optional `STASHPIX_API_KEY` for REST endpoints.
- **pHash/dHash shortlist** before linear SIFT auto-match over registry refs.
- **opencv-contrib-python** replaces `opencv-python` (TPS requires contrib).
- README repositioned as robust image ID / ownership recovery (Digimarc-style pitch);
  LSB no longer claimed to survive resize/crop.

### Breaking
- CLI command renamed from `stego` to `stashpix`.
- LSB wire format v2 (AEAD); 1.2.x stego images need re-embed.
- Registry file format encrypted; legacy plaintext JSON is read once and re-saved.

## [1.2.0] - 2026-07-21

### Added
- **Morph sync layer (SIFT + Thin-Plate Spline + dense DIS optical flow)** as a
  fallback after homography when recovering from non-linear warps (swirl,
  elastic, wave). Exposed as `layer_key=geo_tps`; controlled by
  `ExtractConfig.morph_geo` (on by default).
- Local-MAD outlier filtering and spatially binned TPS control points (default
  128) for more stable non-rigid registration.
- Pytest coverage for morph recovery, mild real-world edits (blur / JPEG /
  crop / piece-on-green), and composite stress (morph + 80% scale + green
  canvas + partial occlusion): `tests/test_morph_geo.py`,
  `tests/test_realistic_attacks.py`, `tests/test_stress_composite.py`, plus
  shared `tests/geo_helpers.py`.

### Changed
- Geometric recovery pipeline: direct → blind/auto homography → **TPS+flow**.
- `large_photo_path` fixture (~768px) for geometric / attack tests.

## [1.1.0] - 2026-07-21

### Added
- Application icon (image stack + dispersing pixels + keyhole) wired into the GUI
  window, both PyInstaller executables, the WiX installer (ARP entry and Start
  Menu shortcut), and the web UI favicon.
- **About / Névjegy** dialog in the GUI showing version, author, GitHub link,
  and license summary.
- **License acceptance (EULA)** on first use, shared across the CLI, GUI, and
  API and recorded per license version at `~/.stashpix/eula_accepted.json`.
- `stego license` command with `--status`, `--show`, `--accept`, and `--reset`;
  a global `--accept-license` flag; the `stashpix_ACCEPT_LICENSE=1` override;
  and a `GET /api/license` endpoint.
- **Encoded Media** term in the license: commercial distribution of watermarked
  or otherwise encoded output (e.g. publication by an online newspaper) requires
  a commercial license.

### Changed
- The transparent-background icon now uses hole-filling and anti-aliased edges so
  it renders cleanly on light and dark surfaces.
- The GUI shows the license terms in its own modal dialog; `stego gui` no longer
  prompts for acceptance in the terminal.
- README documents license acceptance, the Encoded Media clause, and updated
  build/version references.

### Fixed
- `stego gui` is no longer blocked by the CLI acceptance gate in non-interactive
  contexts; the GUI handles acceptance itself.
- Packaging: removed `MERGE()` from the PyInstaller spec so the bundled
  `stashpix-gui.exe` no longer fails with "Failed to load Python DLL" (both
  executables now share one deduplicated `_internal`).
- Packaging: WiX installer builds under v7 (`-acceptEula wix7`, explicit `-arch
  x64`) and resolves the ARP/shortcut icon via a dedicated `IconFile` binding.

## [1.0.0] - 2026-07-21

### Added
- Initial modular `stashpix` package: multi-layer image steganography
  (LSB + robust DCT watermark + geometric synchronization + visible watermark)
  with graceful degradation.
- Unified `stego` CLI, Tkinter desktop GUI, and FastAPI REST API with an
  interactive dashboard and research page.
- Full English/Hungarian internationalization across the CLI, GUI, and API.
- JSON registry with reference-image storage, SIFT-based auto-match, and blind
  reference-free geometric recovery.
- Cross-platform per-user data storage under `~/.stashpix` (with environment
  overrides).
- Standalone bundling via PyInstaller and a Windows MSI via WiX v4+.
- Released under the PolyForm Noncommercial License 1.0.0.

[1.4.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.4.0
[1.3.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.3.0
[1.2.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.2.0
[1.1.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.1.0
[1.0.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.0.0
