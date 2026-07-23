# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Image metadata (EXIF / PNG tags) + a GUI Settings tab.**
  - Embedding now **preserves the source image's EXIF and ICC profile** — the old
    pipeline saved with a bare `img.save()` and silently stripped it.
  - Optional authorship fields (author, copyright, plus the watermark UUID and
    signer fingerprint) are stamped into standard EXIF and PNG text tags so
    ordinary tools show them. CLI: `--author`, `--copyright`, `--no-metadata`.
    Stated loudly everywhere: **metadata is a label, not proof** — it is trivially
    editable; the signature is the proof, and metadata is never consulted for the
    attribution verdict (regression-tested).
  - A persistent settings store (`settings.json`) holds the user's author name,
    copyright, and sign / write-metadata defaults.
  - New **GUI Settings tab**: author + copyright fields, sign and write-metadata
    toggles, identity fingerprint display, and "export public key". The GUI also
    now requires a key (matching the mandatory-key rule) and shows the authorship
    verdict on the Extract tab.
- **Ed25519 authorship signatures — "prove I made this", not just "a watermark
  is present".** The robust watermark binds a UUID to the pixels; it could not,
  on its own, prove *who* claimed the image or *when*. The owner now holds a
  long-term Ed25519 identity; each embed signs a canonical claim binding the
  watermark UUID, the message and a UTC timestamp to the owner's public key.
  Extraction verifies it and reports `authorship: {valid, signer, created}`.
  A verifier needs only the freely-publishable public key.
  - Signing is on by default (`EmbedConfig.sign`), verification too
    (`ExtractConfig.verify_signature`). The signature is checked even when the
    message was recovered from LSB.
  - `stashpix identity` — show the fingerprint / public key, export the public
    key (PEM) to publish, or export/import the private identity as
    password-encrypted PKCS8 for backup and multi-machine use.
  - The identity private key is the owner's **portable root secret**: wrapped at
    rest against file theft, but exportable by design (unlike the machine-bound
    registry key). Losing it means losing the ability to sign as you.
  - Scope, stated plainly: the signature is non-repudiable relative to the
    keyholder. `created` is **self-asserted** — it proves the signer claimed a
    time, not that the time is true. Precedence between competing claims needs a
    trusted timestamp anchor (RFC 3161 / C2PA), tracked next.

## [1.5.0] - 2026-07-22

Security and reliability release. **Contains breaking changes** — see below.

### Removed
- **`edge_match` registry-fingerprint fallback (security).** It resolved a
  registry entry by perceptual-hash similarity alone. Because the robust
  watermark is invisible, the stored reference is ~identical to the *unmarked*
  original, so an image carrying no watermark matched at distance 0 and was
  attributed the owner's message — as was a q30 JPEG of it. The layer was on by
  default, so any caller checking only `msg is not None` got a false positive.
  For a tool whose purpose is proving ownership, that inverts the guarantee.
  Perceptual hashes now only *shortlist* candidates for the SIFT/robust path,
  which still confirms against real watermark bits.
  Removes `ExtractConfig.edge_match*` (6 fields), `Registry.resolve_fingerprint()`
  and `keys.embed_key_tag()`.
- **`robust_auto_adapt` config flag.** With an embed-invariant step the
  non-adaptive path is strictly worse and had no remaining use case.
- Dev probe scripts for the removed feature (one contained a hardcoded personal
  path).

### Fixed
- **The robust DCT layer lost its own ID on clean, lossless roundtrips.**
  `block_slack()` derived the QIM step from Watson contrast masking, whose
  self-masking term scales with the magnitude of the very coefficient QIM
  modulates — so the encoder (clean block) and the blind decoder (watermarked
  block) computed different lattices. Measured: **24.8% median step mismatch**,
  29.2% of coefficients off by >50% (enough to flip parity), and **4/10**
  successful clean roundtrips on `city_architecture.png` at the default
  strength. Now 5.75% median and reliable on every stock cover.
- **Raising `strength` made recovery worse, not better** — 0/10 at strength 6.0
  on five of six covers, contradicting the documented "higher = more robust".
  Same root cause: a larger modulation meant a larger encoder/decoder step
  disagreement.
- **Embeds are verified against the JPEG floor, not just a clean read-back.** On
  a cover already at the canonical width there is no resize round trip, so the
  base strength passed a clean check trivially and shipped a mark too weak to
  survive JPEG. Escalation now targets JPEG q50; if the ladder runs out, the
  image still ships readable but reports `jpeg_verified: False` rather than
  claiming a guarantee that was never checked.

### Security
- **A key is now mandatory.** A missing key silently fell back to the constant
  `DEFAULT_SEED = 1337`: the output looked encrypted, but anyone could read it.
  `EmbedConfig`/`ExtractConfig` reject a missing or blank key, and `-k` is
  required on the CLI.
- **Per-message random salt for the content key (LSB format v2 → v3).**
  `derive_key_bytes` salted every derivation with one hardcoded constant
  (`sha256("stashpix:salt:v1")`), so a password mapped to one globally fixed key
  — precomputable once, reusable against every image the tool ever produced.
  Each embed now draws a fresh 16-byte salt carried in the payload. **v2 and
  earlier payloads are rejected, not read.**
- **Local secrets are bound to the user+machine.** The registry key mixes stored
  random material with a machine fingerprint, so lifting the key file alone onto
  another box does not decrypt a copied registry (registry format v1 → v2; v1 is
  still read and upgraded in place).
- **Pinned digests for the optional AI artifacts.** SyncSeal/WAM checkpoints are
  fed to `torch.load(weights_only=False)` and the vendored repo is imported from
  `sys.path` — both arbitrary code execution. They were fetched with no
  integrity check, and the repo was cloned from whatever `main` pointed at.
  Now SHA-256-pinned, verified before the temp file is published, re-checked on
  every load (including operator-supplied paths), and the repo is fetched at a
  pinned commit. Override with `STASHPIX_ALLOW_UNPINNED_MODELS=1`.

### Note on key portability
Watermark keys stay **password-derived and portable** by design: a decoder only
ever has the password, so machine-binding them would make an image embedded on
one computer unreadable on another. The permutation seed cannot take a random
salt at all — you would need the permutation to read the salt. Confidentiality
therefore rests on the salted AES-GCM content key, not on the seed. Only local
at-rest secrets are machine-bound.

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

[1.5.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.5.0
[1.4.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.4.0
[1.3.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.3.0
[1.2.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.2.0
[1.1.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.1.0
[1.0.0]: https://github.com/arlinamid/stashpix/releases/tag/v1.0.0
