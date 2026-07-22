"""English message catalog."""

CATALOG = {
    # ------------------------------------------------------------------ errors
    "error.generic": "An unexpected error occurred.",
    "error.lossy_format": (
        "[Format check] The {role} file '{path}' has format '{fmt}', which is "
        "LOSSY and would destroy the hidden data. Use PNG, BMP or TIFF."
    ),
    "error.lossy_ext": (
        "[Format check] The extension of '{path}' indicates JPEG (lossy). "
        "Save/open it as PNG."
    ),
    "error.capacity": (
        "[Capacity check] {needed} bits required, {available} available. "
        "This many copies do not fit (max copies for this nsym: {max_copies}). "
        "Reduce copies/nsym or use a larger image."
    ),
    "error.nsym_range": "nsym must be between 1 and 254.",
    "error.copies_range": "copies must be between 1 and 255.",
    "error.decode_header": (
        "[Decode error] The header is unreadable — wrong key, or no hidden data."
    ),
    "error.decode_params": (
        "[Decode error] Corrupt header (invalid parameters) — wrong key, or the "
        "image is too damaged."
    ),
    "error.decode_rs": (
        "[Decode error] Reed-Solomon decoding failed from both the voted and the "
        "individual copies — the image is too damaged or the key is wrong."
    ),
    "error.decode_utf8": (
        "[Decode error] The recovered bytes are not valid UTF-8 ({detail}) — "
        "most likely a wrong key."
    ),
    "error.self_verify_read": "[Self-check] Read-back failed: {detail}",
    "error.self_verify_mismatch": (
        "[Self-check] The post-save decode does not match the original message — "
        "the output file is not trustworthy."
    ),
    "error.robust_self_verify": (
        "[Self-check] The robust watermark did not read back from this cover at "
        "any strength ({detail}). The image is too flat or too small to carry it; "
        "use a larger or more textured cover."
    ),
    "error.key_required": (
        "[Key] A key is required. Without one the payload would be derived from a "
        "fixed constant and anyone could read it. Pass -k/--key (CLI) or set "
        "'key' on the config."
    ),
    "error.dependency_cv2": (
        "Geometric synchronization requires OpenCV: pip install opencv-python"
    ),
    "error.image_open": "Could not open image '{path}': {detail}",
    "error.no_message": "No message provided.",

    # ------------------------------------------------------------- layer names
    "layer.lsb.name": "LSB (full message, lossless)",
    "layer.robust.name": "robust ID + registry",
    "layer.syncseal.name": "SyncSeal geometric sync",
    "layer.wam.name": "WAM localization",
    "layer.visible.name": "visible watermark",
    "layer.geo_tps.name": "morph sync (SIFT + TPS + flow) + registry",
    "layer.none": "no layer recovered a message",

    # -------------------------------------------------------------------- CLI
    "cli.description": (
        "Multi-layer steganography suite — LSB + robust DCT watermark + visible "
        "watermark, with graceful degradation."
    ),
    "cli.help.lang": "Interface language (en/hu).",
    "cli.embed.help": "Embed a message (LSB + robust watermark, optional visible).",
    "cli.extract.help": "Extract a message (tries LSB, then robust ID + registry).",
    "cli.verify_visible.help": "Verify a visible watermark.",
    "cli.gui.help": "Launch the desktop GUI.",
    "cli.serve.help": "Start the REST API / dashboard server.",
    "cli.arg.image": "Input image (PNG/BMP/TIFF).",
    "cli.arg.image_any": "Image to inspect (PNG/BMP/TIFF/JPEG).",
    "cli.arg.output": "Output file path.",
    "cli.arg.message": "Message to hide (text).",
    "cli.arg.message_file": "Message to hide, from a text file.",
    "cli.arg.key": "Key/password for spreading (same key needed to decode).",
    "cli.arg.nsym": "Reed-Solomon ECC bytes per 255-byte block (default 64).",
    "cli.arg.copies": "Number of redundant LSB copies (default 3).",
    "cli.arg.strength": "Base JND watermark strength (method=jnd); embed raises it if needed.",
    "cli.arg.method": "Watermark method: jnd or qim (extract defaults to auto).",
    "cli.arg.q": "Fixed QIM step (method=qim).",
    "cli.arg.visible_text": "Optional visible watermark text (4th layer).",
    "cli.arg.visible_opacity": "Visible watermark opacity (0..1).",
    "cli.arg.wam": "Optional WAM localize fingerprint (downloads model on first use).",
    "cli.arg.syncseal": "Optional SyncSeal geometric sync watermark (downloads model on first use).",
    "cli.arg.try_wam": "Try WAM ROI localization before robust extract.",
    "cli.arg.try_syncseal": "Try SyncSeal unwarp before robust extract.",
    "cli.arg.reference": "Registered (encoded) reference image for geo sync.",
    "cli.arg.output_file": "Write the recovered message here (default: stdout).",
    "cli.arg.show_info": "Print diagnostic info.",
    "cli.arg.host": "Bind host (default 127.0.0.1).",
    "cli.arg.port": "Bind port (default 8000).",
    "cli.embed.done": "Combined embedding done: {path}",
    "cli.embed.robust_id": "  - robust layer ID: {id} (method={method})",
    "cli.embed.lsb": "  - LSB layer: nsym={nsym}, copies={copies}",
    "cli.embed.visible": "  - visible watermark: {text!r} (opacity={opacity})",
    "cli.embed.wam": "  - WAM localization fingerprint enabled",
    "cli.embed.syncseal": "  - SyncSeal geometric sync enabled",
    "cli.extract.header": "--- Recovered message ---",
    "cli.extract.lsb": "[LSB layer] Message recovered: {message!r}",
    "cli.extract.robust": "[Robust layer] LSB lost; ID={id} -> registry -> {message!r}",
    "cli.extract.none": (
        "No layer returned a message (wrong key, or the image is too damaged / "
        "AI-regenerated). If the image was rotated, cropped into another image or "
        "partially occluded, try: stashpix extract-geo -i <image> -r <original> -k <key>"
    ),
    "cli.extract.layer": "layer: {layer}",
    "cli.extract.saved": "Message saved: {path}",
    "cli.verify.present": "Visible watermark: PRESENT (NCC peak={score:.4f}, threshold={threshold})",
    "cli.verify.absent": (
        "Visible watermark: not found (NCC peak={score:.4f}, threshold={threshold}) — "
        "wrong text/key, missing, or heavy crop."
    ),
    "cli.error": "ERROR: {detail}",
    "cli.serve.starting": "Starting server at http://{host}:{port} (web UI: /, research: /research, API docs: /docs)",
    "cli.serve.need_api": (
        "The API requires extra packages: pip install \"stashpix[api]\" "
        "(or fastapi uvicorn python-multipart)."
    ),

    # -------------------------------------------------------------------- GUI
    "gui.title": "Steganography — multi-layer (LSB + robust DCT + visible)",
    "gui.tab.encode": "  Hide  ",
    "gui.tab.decode": "  Extract  ",
    "gui.language": "Language:",
    "gui.about": "About",
    "gui.about.title": "About stashpix",
    "gui.about.body": (
        "stashpix v{version}\n"
        "Multi-layer image steganography — LSB + robust DCT + visible watermark.\n\n"
        "Author: Rózsavölgyi János\n"
        "GitHub: https://github.com/arlinamid\n\n"
        "License: PolyForm Noncommercial 1.0.0\n"
        "Free for personal / noncommercial use; commercial use requires approval.\n"
        "Commercial distribution of encoded media (e.g. by an online newspaper)\n"
        "requires a commercial license."
    ),
    "gui.about.visit": "Open GitHub",
    "gui.input_image": "Input image:",
    "gui.output_file": "Output file:",
    "gui.browse": "Browse…",
    "gui.save_as": "Save as…",
    "gui.key": "Key (password):",
    "gui.rs_ecc": "RS ECC (nsym):",
    "gui.copies": "Copies:",
    "gui.max": "Max",
    "gui.self_verify": "Self-healing check",
    "gui.strength": "Watermark strength:",
    "gui.visible_text": "Visible watermark (optional):",
    "gui.enable_wam": "WAM localize fingerprint (optional AI, downloads on first use)",
    "gui.enable_syncseal": "SyncSeal geometric sync (optional AI, downloads on first use)",
    "gui.try_wam": "Try WAM ROI localize",
    "gui.try_syncseal": "Try SyncSeal unwarp",
    "gui.encode_hint": (
        "Both invisible layers are embedded. LSB (nsym/copies) = full message, "
        "crop/repaint tolerant. Robust DCT watermark = ID for the registry, "
        "JPEG/resize tolerant. Strength is in JND units (perceptually adaptive): "
        "~1 is the visibility threshold, higher = more robust + more visible. "
        "Filling 'Visible watermark' also stamps a human-visible diagonal mark (4th layer). "
        "Optional WAM / SyncSeal need PyTorch + first-use model download (~480 MB); "
        "CPU is fine. Leave them off for a light, invisible embed."
    ),
    "gui.message": "Message to hide:",
    "gui.encode_btn": "Hide message",
    "gui.stashpix_image": "Stego image:",
    "gui.reference_image": "Reference (optional):",
    "gui.reference_hint": "For a suspicious/altered image (rotated, cropped, placed "
                          "into another picture) pick the original here to re-align it.",
    "gui.decoded_message": "Recovered message:",
    "gui.decode_btn": "Extract message",
    "gui.copy_clipboard": "Copy to clipboard",
    "gui.visible_verify_frame": "Visible watermark check (4th layer)",
    "gui.visible_expected": "Expected text:",
    "gui.verify_btn": "Verify",
    "gui.status.ready": "Ready.",
    "gui.status.encoding": "Combined embedding… (may download AI models on first SyncSeal/WAM use)",
    "gui.status.decoding": "Extracting… (WAM/SyncSeal if enabled)",
    "gui.status.verifying": "Verifying visible watermark…",
    "gui.status.saved": "Done — saved: {path}",
    "gui.status.decoded": "Done — message extracted.",
    "gui.status.no_message": "No recoverable message.",
    "gui.status.visible_present": "Visible watermark: present.",
    "gui.status.visible_absent": "Visible watermark: no match.",
    "gui.status.clipboard": "Message copied to clipboard.",
    "gui.status.error": "Error.",
    "gui.msg.error": "Error",
    "gui.msg.success": "Success",
    "gui.msg.encode_ok": (
        "The message was hidden in every layer.\n\nSaved file:\n{path}\n\n"
        "Robust layer ID (registry):\n{id}"
    ),
    "gui.err.pick_input": "Choose a valid input image.",
    "gui.err.pick_output": "Provide an output file.",
    "gui.err.empty_message": "The message is empty.",
    "gui.err.int_fields": "nsym and copies must be integers.",
    "gui.err.nsym_range": "nsym must be between 1 and 254.",
    "gui.err.copies_range": "copies must be between 1 and 255.",
    "gui.err.strength_number": "Watermark strength must be a number.",
    "gui.err.pick_image": "Choose a valid image.",
    "gui.err.expected_text": "Enter the expected visible watermark text.",
    "gui.cap.image": "Image: {w}×{h}px — capacity {cap} bits",
    "gui.cap.max": " • max copies for this message (nsym={nsym}): {max}",
    "gui.cap.nofit": " • the message does NOT fit (larger image / smaller nsym)",
    "gui.cap.needmsg": " • enter a message to compute max copies",
    "gui.info.lsb": " • source: {source}, {copies} copies, {errors} RS errors corrected",
    "gui.info.id": " • ID: {id}",
    "gui.visible.present": "OK — visible watermark PRESENT (NCC={score:.3f} >= {threshold})",
    "gui.visible.absent": (
        "Not found (NCC={score:.3f} < {threshold}) — wrong text/key, missing, or heavy crop."
    ),

    # -------------------------------------------------------------------- API
    "api.title": "stashpix API",
    "api.embed.ok": "Message embedded successfully.",
    "api.extract.ok": "Message extracted.",
    "api.extract.none": "No layer recovered a message.",
    "api.verify.ok": "Verification complete.",
    "api.err.no_file": "No image file provided.",
    "api.err.no_message": "No message provided.",

    # ----------------------------------------------------------------- web UI
    "web.title": "stashpix",
    "web.subtitle": "Multi-layer steganography — LSB + robust DCT watermark + visible watermark",
    "web.status.online": "online",
    "web.status.offline": "offline",
    "web.label.version": "version",
    "web.label.registry": "registry entries",
    "web.label.geo": "geo (SIFT)",
    "web.language": "Language",
    "web.tab.embed": "Embed",
    "web.tab.extract": "Extract",
    "web.tab.verify": "Verify visible",
    "web.tab.registry": "Registry",
    "web.tab.about": "About",
    "web.field.cover": "Cover image",
    "web.field.image": "Image",
    "web.field.message": "Message",
    "web.field.key": "Key (password)",
    "web.field.copies": "LSB copies",
    "web.field.nsym": "RS ECC (nsym)",
    "web.field.strength": "Watermark strength",
    "web.field.visible": "Visible watermark text (optional)",
    "web.field.expected": "Expected visible text",
    "web.field.reference": "Reference image (optional — for suspicious/altered images)",
    "web.field.reference_hint": "If the image looks rotated, cropped or placed into "
                               "another picture, add the original here to re-align it.",
    "web.btn.embed": "Embed & download",
    "web.btn.extract": "Extract",
    "web.btn.verify": "Verify",
    "web.btn.refresh": "Refresh",
    "web.btn.choose": "Choose file…",
    "web.msg.processing": "Processing…",
    "web.msg.embed_ok": "Embedded. Robust ID: {id}",
    "web.msg.download": "Download stashpix image",
    "web.msg.no_message": "No layer recovered a message.",
    "web.msg.layer": "Recovering layer: {layer}",
    "web.msg.present": "PRESENT — the visible watermark matches (NCC {score}).",
    "web.msg.absent": "Not found (NCC {score}) — wrong text/key, missing, or heavy crop.",
    "web.msg.error": "Error",
    "web.registry.title": "Current registry state",
    "web.registry.id": "ID",
    "web.registry.message": "Message",
    "web.registry.created": "Created",
    "web.registry.source": "Source",
    "web.registry.output": "Output",
    "web.registry.empty": "The registry is empty — embed something first.",
    "web.registry.autorefresh": "Auto-refresh",
    "web.about.body": (
        "Four layers with graceful degradation: LSB carries the full message "
        "(crop/repaint tolerant), the robust DCT watermark carries an ID resolved "
        "via the registry (JPEG/resize tolerant), the geometric synchronizer "
        "re-aligns transformed images, and the visible watermark adds a "
        "human-readable, verifiable stamp."
    ),
    "web.about.research": "Open the research dashboard",

    # ------------------------------------------------------------------- EULA
    "eula.title": "License Agreement — stashpix",
    "eula.intro": (
        "stashpix v{version} is licensed under the PolyForm Noncommercial "
        "License 1.0.0 with an additional Encoded Media term. Please read and "
        "accept the terms before using the software."
    ),
    "eula.terms": (
        "By accepting, you agree that:\n"
        "  • Personal and other NONCOMMERCIAL use is free (including modifying "
        "and redistributing under the same terms).\n"
        "  • COMMERCIAL use of the software requires a separate commercial "
        "license, granted only with the author's prior written approval.\n"
        "  • ENCODED MEDIA: files you create with this software that carry a "
        "watermark or hidden payload may be created and shared for noncommercial "
        "purposes, but COMMERCIAL DISTRIBUTION of such media (for example, "
        "publication by an online newspaper or any for-profit outlet) requires a "
        "commercial license.\n"
        "  • The software is provided AS IS, without warranty of any kind.\n"
        "Full text: see the LICENSE file. Commercial licensing / contact: "
        "https://github.com/arlinamid"
    ),
    "eula.accept": "I Accept",
    "eula.decline": "Decline",
    "eula.view_full": "View full LICENSE",
    "eula.prompt": "Do you accept these terms? [y/N]: ",
    "eula.accepted": "License terms accepted (v{version}). Recorded at {path}.",
    "eula.declined": "License terms not accepted — exiting.",
    "eula.required": (
        "You must accept the license terms before using stashpix. Run an "
        "interactive terminal and answer the prompt, pass --accept-license, or "
        "set stashpix_ACCEPT_LICENSE=1. Full text: LICENSE."
    ),
    "eula.status.accepted": "Accepted: v{version} on {when} (via {method}).",
    "eula.status.not_accepted": "Not accepted yet.",
    "cli.license.help": "Show the license, acceptance status, or accept the terms.",
    "cli.arg.accept_license": "Accept the license terms non-interactively.",
    "cli.arg.license_status": "Show current acceptance status and exit.",
    "cli.arg.license_show": "Print the full LICENSE text and exit.",
    "cli.arg.license_reset": "Reset acceptance (the terms will be asked again).",
    "eula.reset.done": "License acceptance was reset — the terms will be asked again next time.",
    "eula.reset.none": "No acceptance record found; nothing to reset.",
    "cli.license.header": "stashpix license status",
}
