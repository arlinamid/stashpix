"""Unified command-line interface: ``stashpix <command> ...``.

Commands: embed, extract, extract-geo, verify-visible, gui, serve, license.
A global ``--lang`` selects the interface language (en/hu).
"""

from __future__ import annotations

import sys
import argparse
from typing import Optional

from .config import (
    EmbedConfig,
    ExtractConfig,
    VerifyConfig,
    DEFAULT_NSYM,
    DEFAULT_COPIES,
    DEFAULT_METHOD,
    DEFAULT_Q,
    DEFAULT_STRENGTH,
    DEFAULT_VISIBLE_OPACITY,
    DEFAULT_VISIBLE_THRESHOLD,
)
from .engine import StegoEngine
from .exceptions import StegoError
from .i18n import t, set_locale, available_locales
from . import eula


def _ensure_utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stashpix", description=t("cli.description"))
    p.add_argument("--lang", choices=available_locales(), default=None,
                   help=t("cli.help.lang"))
    p.add_argument("--accept-license", action="store_true",
                   help=t("cli.arg.accept_license"))
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("embed", help=t("cli.embed.help"))
    e.add_argument("-i", "--image", required=True, help=t("cli.arg.image"))
    e.add_argument("-o", "--output", required=True, help=t("cli.arg.output"))
    g = e.add_mutually_exclusive_group(required=True)
    g.add_argument("-m", "--message", help=t("cli.arg.message"))
    g.add_argument("--message-file", help=t("cli.arg.message_file"))
    e.add_argument("-k", "--key", required=True, help=t("cli.arg.key"))
    e.add_argument("--nsym", type=int, default=DEFAULT_NSYM, help=t("cli.arg.nsym"))
    e.add_argument("--copies", type=int, default=DEFAULT_COPIES, help=t("cli.arg.copies"))
    e.add_argument("--method", choices=["jnd", "qim"], default=DEFAULT_METHOD,
                   help=t("cli.arg.method"))
    e.add_argument("--strength", type=float, default=DEFAULT_STRENGTH, help=t("cli.arg.strength"))
    e.add_argument("-Q", type=float, default=DEFAULT_Q, help=t("cli.arg.q"))
    e.add_argument("--visible-text", default=None, help=t("cli.arg.visible_text"))
    e.add_argument("--visible-opacity", type=float, default=DEFAULT_VISIBLE_OPACITY,
                   help=t("cli.arg.visible_opacity"))
    e.add_argument("--wam", action="store_true", help=t("cli.arg.wam"))
    e.add_argument("--syncseal", action="store_true", help=t("cli.arg.syncseal"))
    e.set_defaults(func=_cmd_embed)

    x = sub.add_parser("extract", help=t("cli.extract.help"))
    x.add_argument("-i", "--image", required=True, help=t("cli.arg.image_any"))
    x.add_argument("-k", "--key", required=True, help=t("cli.arg.key"))
    x.add_argument("--method", choices=["jnd", "qim"], default=None, help=t("cli.arg.method"))
    x.add_argument("--strength", type=float, default=DEFAULT_STRENGTH, help=t("cli.arg.strength"))
    x.add_argument("-Q", type=float, default=DEFAULT_Q, help=t("cli.arg.q"))
    x.add_argument("--output-file", default=None, help=t("cli.arg.output_file"))
    x.add_argument("--show-info", action="store_true", help=t("cli.arg.show_info"))
    x.add_argument("--try-wam", action="store_true", help=t("cli.arg.try_wam"))
    x.add_argument("--try-syncseal", action="store_true", help=t("cli.arg.try_syncseal"))
    x.set_defaults(func=_cmd_extract)

    gg = sub.add_parser("extract-geo", help=t("cli.extract.help"))
    gg.add_argument("-i", "--image", required=True, help=t("cli.arg.image_any"))
    gg.add_argument("-r", "--reference", required=True, help=t("cli.arg.reference"))
    gg.add_argument("-k", "--key", required=True, help=t("cli.arg.key"))
    gg.add_argument("--method", choices=["jnd", "qim"], default=None, help=t("cli.arg.method"))
    gg.add_argument("--strength", type=float, default=DEFAULT_STRENGTH, help=t("cli.arg.strength"))
    gg.add_argument("--show-info", action="store_true", help=t("cli.arg.show_info"))
    gg.add_argument("--try-wam", action="store_true", help=t("cli.arg.try_wam"))
    gg.add_argument("--try-syncseal", action="store_true", help=t("cli.arg.try_syncseal"))
    gg.set_defaults(func=_cmd_extract_geo)

    v = sub.add_parser("verify-visible", help=t("cli.verify_visible.help"))
    v.add_argument("-i", "--image", required=True, help=t("cli.arg.image_any"))
    v.add_argument("-t", "--text", required=True, help=t("cli.arg.visible_text"))
    v.add_argument("-k", "--key", default=None, help=t("cli.arg.key"))
    v.add_argument("--threshold", type=float, default=DEFAULT_VISIBLE_THRESHOLD)
    v.set_defaults(func=_cmd_verify_visible)

    idp = sub.add_parser("identity", help=t("cli.identity.help"))
    idp.add_argument("--show", action="store_true", help=t("cli.arg.identity_show"))
    idp.add_argument("--create", action="store_true", help=t("cli.arg.identity_create"))
    idp.add_argument("--export-public", metavar="PATH", help=t("cli.arg.identity_export_public"))
    idp.add_argument("--export", metavar="PATH", help=t("cli.arg.identity_export"))
    idp.add_argument("--import", dest="import_path", metavar="PATH",
                     help=t("cli.arg.identity_import"))
    idp.add_argument("--password", default=None, help=t("cli.arg.identity_password"))
    idp.add_argument("--overwrite", action="store_true", help=t("cli.arg.identity_overwrite"))
    idp.set_defaults(func=_cmd_identity)

    gui = sub.add_parser("gui", help=t("cli.gui.help"))
    gui.set_defaults(func=_cmd_gui)

    srv = sub.add_parser("serve", help=t("cli.serve.help"))
    srv.add_argument("--host", default="127.0.0.1", help=t("cli.arg.host"))
    srv.add_argument("--port", type=int, default=8000, help=t("cli.arg.port"))
    srv.set_defaults(func=_cmd_serve)

    lic = sub.add_parser("license", help=t("cli.license.help"))
    lic.add_argument("--accept", action="store_true", help=t("cli.arg.accept_license"))
    lic.add_argument("--status", action="store_true", help=t("cli.arg.license_status"))
    lic.add_argument("--show", action="store_true", help=t("cli.arg.license_show"))
    lic.add_argument("--reset", action="store_true", help=t("cli.arg.license_reset"))
    lic.set_defaults(func=_cmd_license)

    return p


# ----------------------------------------------------------------------
# Command handlers
# ----------------------------------------------------------------------

def _cmd_embed(args) -> int:
    if args.message is not None:
        message = args.message
    else:
        with open(args.message_file, "r", encoding="utf-8") as f:
            message = f.read()

    engine = StegoEngine()
    config = EmbedConfig(
        key=args.key, lsb_nsym=args.nsym, lsb_copies=args.copies,
        robust_method=args.method, robust_strength=args.strength, robust_q=args.Q,
        visible_text=args.visible_text, visible_opacity=args.visible_opacity,
        enable_wam=args.wam, enable_syncseal=args.syncseal,
    )
    result = engine.embed_file(args.image, message, args.output, config)
    print(t("cli.embed.done", path=result.output_path))
    if result.robust_id:
        print(t("cli.embed.robust_id", id=result.robust_id, method=args.method))
    print(t("cli.embed.lsb", nsym=args.nsym, copies=args.copies))
    if args.visible_text:
        print(t("cli.embed.visible", text=args.visible_text, opacity=args.visible_opacity))
    if args.wam:
        print(t("cli.embed.wam"))
    if args.syncseal:
        print(t("cli.embed.syncseal"))
    return 0


def _cmd_extract(args) -> int:
    engine = StegoEngine()
    config = ExtractConfig(key=args.key, robust_method=args.method,
                           robust_strength=args.strength, robust_q=args.Q,
                           try_wam=args.try_wam, try_syncseal=args.try_syncseal)
    message, info = engine.extract_file(args.image, config)
    return _emit_extract(args, message, info)


def _cmd_extract_geo(args) -> int:
    engine = StegoEngine()
    config = ExtractConfig(key=args.key, robust_method=args.method,
                           robust_strength=args.strength,
                           try_wam=args.try_wam, try_syncseal=args.try_syncseal)
    message, info = engine.extract_geo_file(args.image, args.reference, config)
    return _emit_extract(args, message, info)


def _emit_extract(args, message: Optional[str], info: dict) -> int:
    if message is None:
        print(t("cli.extract.none"))
        return 2
    if getattr(args, "output_file", None):
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(message)
        print(t("cli.extract.saved", path=args.output_file))
    else:
        print(t("cli.extract.header"))
        print(message)
    auth = info.get("authorship")
    if auth:
        if auth.get("valid"):
            print(t("cli.extract.signed_ok", signer=auth.get("signer"),
                    created=auth.get("created")))
        else:
            print(t("cli.extract.signed_bad", reason=auth.get("reason")))
    if getattr(args, "show_info", False):
        print(t("cli.extract.layer", layer=info.get("layer")))
        for k, val in info.items():
            print(f"  {k}: {val}")
    return 0


def _cmd_identity(args) -> int:
    from .core import authorship

    if args.import_path:
        if not args.password:
            print(t("error.identity_export_password"))
            return 2
        with open(args.import_path, "rb") as f:
            authorship.import_identity(f.read(), args.password, overwrite=args.overwrite)
        print(t("cli.identity.imported",
                fp=authorship.identity_fingerprint(create=False)))
        return 0

    priv = authorship.load_or_create_identity(create=args.create or args.show
                                              or bool(args.export_public) or bool(args.export))
    if priv is None:
        print(t("cli.identity.none"))
        return 2

    fp = authorship.public_fingerprint(authorship.public_key_bytes(priv))
    if args.export_public:
        with open(args.export_public, "w", encoding="utf-8") as f:
            f.write(authorship.export_public_pem(priv))
        print(t("cli.identity.exported_public", path=args.export_public, fp=fp))
    if args.export:
        if not args.password:
            print(t("error.identity_export_password"))
            return 2
        with open(args.export, "wb") as f:
            f.write(authorship.export_identity(priv, args.password))
        print(t("cli.identity.exported", path=args.export))
    if args.show or not (args.export_public or args.export):
        print(t("cli.identity.fingerprint", fp=fp))
        print(authorship.export_public_pem(priv).strip())
    return 0


def _cmd_verify_visible(args) -> int:
    engine = StegoEngine()
    present, score, _info = engine.verify_visible_file(
        args.image, VerifyConfig(text=args.text, key=args.key, threshold=args.threshold))
    key = "cli.verify.present" if present else "cli.verify.absent"
    print(t(key, score=score, threshold=args.threshold))
    return 0 if present else 2


def _cmd_gui(args) -> int:
    if getattr(args, "accept_license", False) and not eula.is_accepted():
        eula.record_acceptance("flag")
    from .gui.app import main as gui_main
    gui_main()
    return 0


def _cmd_license(args) -> int:
    if args.show:
        print(eula.license_text())
        return 0
    if args.reset:
        removed = eula.reset_acceptance()
        print(t("eula.reset.done" if removed else "eula.reset.none"))
        return 0
    if args.accept:
        path = eula.record_acceptance("cli")
        print(t("eula.accepted", version=eula.__version__, path=path))
        return 0
    print(t("cli.license.header"))
    print(eula.status_text())
    print()
    print(eula.summary_text())
    return 0


def _cmd_serve(args) -> int:
    try:
        import uvicorn
        from .api.app import create_app
    except ImportError:
        print(t("cli.serve.need_api"), file=sys.stderr)
        return 1
    print(t("cli.serve.starting", host=args.host, port=args.port))
    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def main(argv=None) -> int:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(argv)
    set_locale(args.lang)
    # "license" manages acceptance itself; "gui" shows its own modal dialog.
    if args.command not in ("license", "gui") and not eula.is_accepted():
        if not eula.ensure_accepted_cli(getattr(args, "accept_license", False)):
            return 3
    try:
        return args.func(args)
    except StegoError as e:
        print(t("cli.error", detail=str(e)), file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(t("cli.error", detail=str(e)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
