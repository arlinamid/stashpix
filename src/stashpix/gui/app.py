"""Tkinter desktop GUI wired to :class:`stashpix.stashpixEngine`, with live i18n.

All labels are registered with :meth:`StegoGUI._tr`; switching the language
combobox re-applies every registered translation without losing field values.
"""

from __future__ import annotations

import os
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from PIL import Image, ImageTk

from .. import __version__
from .. import eula
from ..engine import StegoEngine
from ..config import (
    EmbedConfig,
    ExtractConfig,
    VerifyConfig,
    DEFAULT_NSYM,
    DEFAULT_STRENGTH,
    DEFAULT_VISIBLE_THRESHOLD,
)
from ..core.coding import RSCodec
from ..layers.lsb import header_repeats, HEADER_ENC_BITS
from ..paths import asset_path
from ..i18n import t, set_locale, get_locale, available_locales

LOSSLESS_EXT = [
    ("PNG/BMP/TIFF", "*.png *.bmp *.tif *.tiff"),
    ("PNG", "*.png"), ("BMP", "*.bmp"), ("TIFF", "*.tif *.tiff"),
    ("*", "*.*"),
]
DECODE_EXT = [
    ("Images", "*.png *.bmp *.tif *.tiff *.jpg *.jpeg *.webp"),
    ("JPEG", "*.jpg *.jpeg"), ("PNG", "*.png"), ("*", "*.*"),
]


class StegoGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.engine = StegoEngine()
        self._result_q: "queue.Queue" = queue.Queue()
        self._preview_refs = {}
        self._tr_items = []          # list of (setter_callable, key)
        self._max_copies = 255

        self.geometry("900x680")
        self.minsize(780, 600)
        self._set_window_icon()
        self._build_style()
        self._build_ui()
        self._apply_language()
        self.after(100, self._poll_queue)

    def _set_window_icon(self):
        """Apply the app icon: .ico on Windows, PNG via iconphoto elsewhere."""
        ico = asset_path("icon.ico")
        if ico is not None:
            try:
                self.iconbitmap(default=str(ico))
                return
            except tk.TclError:
                pass
        png = asset_path("icon-256.png") or asset_path("icon.png")
        if png is not None:
            try:
                self._icon_photo = ImageTk.PhotoImage(Image.open(png))
                self.iconphoto(True, self._icon_photo)
            except Exception:  # noqa: BLE001
                pass

    def show_eula_modal(self) -> bool:
        """Show a modal license dialog. Returns True if the user accepts.

        No-op returning True when the terms were already accepted.
        """
        if eula.is_accepted():
            return True
        win = tk.Toplevel(self)
        win.title(t("eula.title"))
        win.transient(self)
        win.resizable(False, False)
        try:
            ico = asset_path("icon.ico")
            if ico is not None:
                win.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

        result = {"accepted": False}
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=t("eula.title"), font=("Segoe UI", 12, "bold")).pack(
            anchor="w", pady=(0, 8))
        box = scrolledtext.ScrolledText(frame, width=78, height=18, wrap="word",
                                        font=("Segoe UI", 9))
        box.pack(fill="both", expand=True)
        box.insert("1.0", eula.summary_text())
        box.configure(state="disabled")

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(12, 0))

        def _view_full():
            self._show_license_text()

        def _accept():
            eula.record_acceptance("gui")
            result["accepted"] = True
            win.destroy()

        def _decline():
            result["accepted"] = False
            win.destroy()

        ttk.Button(btns, text=t("eula.view_full"), command=_view_full).pack(side="left")
        ttk.Button(btns, text=t("eula.decline"), command=_decline).pack(side="right")
        ttk.Button(btns, text=t("eula.accept"), command=_accept,
                   style="Accent.TButton").pack(side="right", padx=(0, 8))

        win.protocol("WM_DELETE_WINDOW", _decline)
        win.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - win.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - win.winfo_height()) // 4)
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.grab_set()
        self.wait_window(win)
        return result["accepted"]

    def _show_license_text(self):
        win = tk.Toplevel(self)
        win.title(t("eula.view_full"))
        win.transient(self)
        box = scrolledtext.ScrolledText(win, width=90, height=32, wrap="word",
                                        font=("Consolas", 9))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("1.0", eula.license_text())
        box.configure(state="disabled")
        ttk.Button(win, text="OK", command=win.destroy).pack(pady=(0, 8))
        win.grab_set()

    def _show_about(self):
        """Modal About dialog: icon, version/author/license text, GitHub link."""
        github_url = "https://github.com/arlinamid"
        win = tk.Toplevel(self)
        win.title(t("gui.about.title"))
        win.transient(self)
        win.resizable(False, False)
        try:
            ico = asset_path("icon.ico")
            if ico is not None:
                win.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        png = asset_path("icon-256.png") or asset_path("icon.png")
        if png is not None:
            try:
                img = Image.open(png)
                img.thumbnail((96, 96))
                self._about_photo = ImageTk.PhotoImage(img)
                ttk.Label(frame, image=self._about_photo).grid(
                    row=0, column=0, rowspan=2, sticky="n", padx=(0, 14))
            except Exception:  # noqa: BLE001
                pass

        body = ttk.Label(frame, justify="left",
                         text=t("gui.about.body", version=__version__))
        body.grid(row=0, column=1, sticky="w")

        btns = ttk.Frame(frame)
        btns.grid(row=1, column=1, sticky="e", pady=(14, 0))
        ttk.Button(btns, text=t("gui.about.visit"),
                   command=lambda: webbrowser.open(github_url)).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="OK", command=win.destroy).pack(side="left")

        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.grab_set()

    # ------------------------------------------------------------ i18n glue
    def _tr(self, setter, key):
        """Register a translatable target: setter(text) is called now and on
        every language change."""
        self._tr_items.append((setter, key))
        setter(t(key))

    def _apply_language(self):
        self.title(t("gui.title"))
        for setter, key in self._tr_items:
            setter(t(key))

    def _on_language_change(self, *_):
        set_locale(self.lang_var.get())
        self._apply_language()
        self._recalc_max_copies()

    # ------------------------------------------------------------------ UI
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Hint.TLabel", foreground="#666")

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(8, 0))
        lbl = ttk.Label(top)
        lbl.pack(side="left")
        self._tr(lambda s, w=lbl: w.configure(text=s), "gui.language")
        self.lang_var = tk.StringVar(value=get_locale())
        lang = ttk.Combobox(top, values=available_locales(), width=6,
                            state="readonly", textvariable=self.lang_var)
        lang.pack(side="left", padx=6)
        lang.bind("<<ComboboxSelected>>", self._on_language_change)

        about_btn = ttk.Button(top, command=self._show_about)
        about_btn.pack(side="right")
        self._tr(lambda s, w=about_btn: w.configure(text=s), "gui.about")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(6, 4))
        self.encode_tab = ttk.Frame(self.nb, padding=12)
        self.decode_tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(self.encode_tab)
        self.nb.add(self.decode_tab)
        self._tr(lambda s: self.nb.tab(0, text=s), "gui.tab.encode")
        self._tr(lambda s: self.nb.tab(1, text=s), "gui.tab.decode")

        self._build_encode_tab()
        self._build_decode_tab()

        self.status = tk.StringVar(value=t("gui.status.ready"))
        bar = ttk.Frame(self)
        bar.pack(fill="x", side="bottom")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=140)
        self.progress.pack(side="right", padx=8, pady=4)
        ttk.Label(bar, textvariable=self.status, style="Hint.TLabel").pack(
            side="left", padx=10, pady=4)

    def _mk_label(self, parent, key, **grid):
        w = ttk.Label(parent)
        w.grid(**grid)
        self._tr(lambda s, ww=w: ww.configure(text=s), key)
        return w

    def _mk_button(self, parent, key, command, style=None, **grid):
        w = ttk.Button(parent, command=command)
        if style:
            w.configure(style=style)
        w.grid(**grid)
        self._tr(lambda s, ww=w: ww.configure(text=s), key)
        return w

    # ---------------------------------------------------------- ENCODE tab
    def _build_encode_tab(self):
        tb = self.encode_tab
        tb.columnconfigure(1, weight=1)

        self._mk_label(tb, "gui.input_image", row=0, column=0, sticky="w", pady=4)
        self.enc_input = tk.StringVar()
        ttk.Entry(tb, textvariable=self.enc_input).grid(row=0, column=1, sticky="ew", padx=6)
        self._mk_button(tb, "gui.browse", self._pick_encode_input, row=0, column=2)

        self._mk_label(tb, "gui.output_file", row=1, column=0, sticky="w", pady=4)
        self.enc_output = tk.StringVar()
        ttk.Entry(tb, textvariable=self.enc_output).grid(row=1, column=1, sticky="ew", padx=6)
        self._mk_button(tb, "gui.save_as", self._pick_encode_output, row=1, column=2)

        opt = ttk.Frame(tb)
        opt.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        opt.columnconfigure(1, weight=1)

        self._mk_label(opt, "gui.key", row=0, column=0, sticky="w")
        self.enc_key = tk.StringVar()
        ttk.Entry(opt, textvariable=self.enc_key, show="•").grid(row=0, column=1, sticky="ew", padx=6)

        self._mk_label(opt, "gui.rs_ecc", row=0, column=2, sticky="w", padx=(10, 0))
        self.enc_nsym = tk.IntVar(value=DEFAULT_NSYM)
        ttk.Spinbox(opt, from_=1, to=254, width=5, textvariable=self.enc_nsym,
                    command=self._recalc_max_copies).grid(row=0, column=3, padx=6)

        self._mk_label(opt, "gui.copies", row=0, column=4, sticky="w", padx=(10, 0))
        self.enc_copies = tk.IntVar(value=1)
        self.enc_copies_spin = ttk.Spinbox(opt, from_=1, to=255, width=5,
                                           textvariable=self.enc_copies)
        self.enc_copies_spin.grid(row=0, column=5, padx=6)
        self._mk_button(opt, "gui.max", self._set_max_copies, row=0, column=6, padx=(2, 0))

        self.enc_verify = tk.BooleanVar(value=True)
        cb = ttk.Checkbutton(opt, variable=self.enc_verify)
        cb.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._tr(lambda s, w=cb: w.configure(text=s), "gui.self_verify")

        self._mk_label(opt, "gui.strength", row=1, column=2, sticky="w", padx=(10, 0), pady=(6, 0))
        self.enc_strength = tk.DoubleVar(value=DEFAULT_STRENGTH)
        ttk.Spinbox(opt, from_=0.5, to=5.0, increment=0.1, width=5,
                    textvariable=self.enc_strength).grid(row=1, column=3, padx=6, pady=(6, 0))

        self._mk_label(opt, "gui.visible_text", row=2, column=0, sticky="w", pady=(8, 0))
        self.enc_visible = tk.StringVar()
        ttk.Entry(opt, textvariable=self.enc_visible).grid(
            row=2, column=1, columnspan=5, sticky="ew", padx=6, pady=(8, 0))

        self.enc_wam = tk.BooleanVar(value=False)
        cb_wam = ttk.Checkbutton(opt, variable=self.enc_wam)
        cb_wam.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._tr(lambda s, w=cb_wam: w.configure(text=s), "gui.enable_wam")

        self.enc_syncseal = tk.BooleanVar(value=False)
        cb_sync = ttk.Checkbutton(opt, variable=self.enc_syncseal)
        cb_sync.grid(row=3, column=2, columnspan=4, sticky="w", pady=(6, 0), padx=(10, 0))
        self._tr(lambda s, w=cb_sync: w.configure(text=s), "gui.enable_syncseal")

        hint = ttk.Label(tb, style="Hint.TLabel", wraplength=820, justify="left")
        hint.grid(row=3, column=0, columnspan=3, sticky="w")
        self._tr(lambda s, w=hint: w.configure(text=s), "gui.encode_hint")

        self._mk_label(tb, "gui.message", row=4, column=0, sticky="nw", pady=(10, 4))
        self.enc_msg = scrolledtext.ScrolledText(tb, height=7, wrap="word", font=("Segoe UI", 10))
        self.enc_msg.grid(row=4, column=1, columnspan=2, sticky="nsew", padx=6, pady=(10, 4))
        self.enc_msg.bind("<KeyRelease>", lambda _e: self._recalc_max_copies())
        tb.rowconfigure(4, weight=1)

        bottom = ttk.Frame(tb)
        bottom.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        bottom.columnconfigure(0, weight=1)
        self.enc_cap = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.enc_cap.grid(row=0, column=0, sticky="w")
        self.enc_preview = ttk.Label(bottom)
        self.enc_preview.grid(row=0, column=1, rowspan=2, sticky="e", padx=6)
        self.enc_btn = self._mk_button(bottom, "gui.encode_btn", self._do_encode,
                                       style="Accent.TButton", row=1, column=0,
                                       sticky="w", pady=6)

    # ---------------------------------------------------------- DECODE tab
    def _build_decode_tab(self):
        tb = self.decode_tab
        tb.columnconfigure(1, weight=1)

        self._mk_label(tb, "gui.stashpix_image", row=0, column=0, sticky="w", pady=4)
        self.dec_input = tk.StringVar()
        ttk.Entry(tb, textvariable=self.dec_input).grid(row=0, column=1, sticky="ew", padx=6)
        self._mk_button(tb, "gui.browse", self._pick_decode_input, row=0, column=2)

        self._mk_label(tb, "gui.reference_image", row=1, column=0, sticky="w", pady=4)
        self.dec_ref = tk.StringVar()
        ttk.Entry(tb, textvariable=self.dec_ref).grid(row=1, column=1, sticky="ew", padx=6)
        self._mk_button(tb, "gui.browse", self._pick_decode_reference, row=1, column=2)
        ref_hint = ttk.Label(tb, style="Hint.TLabel", wraplength=820, justify="left")
        ref_hint.grid(row=2, column=1, columnspan=2, sticky="w")
        self._tr(lambda s, w=ref_hint: w.configure(text=s), "gui.reference_hint")

        self._mk_label(tb, "gui.key", row=3, column=0, sticky="w", pady=4)
        self.dec_key = tk.StringVar()
        ttk.Entry(tb, textvariable=self.dec_key, show="•").grid(row=3, column=1, sticky="ew", padx=6)
        self.dec_btn = self._mk_button(tb, "gui.decode_btn", self._do_decode,
                                       style="Accent.TButton", row=3, column=2, padx=(6, 0))

        ai = ttk.Frame(tb)
        ai.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.dec_try_wam = tk.BooleanVar(value=False)
        cb_tw = ttk.Checkbutton(ai, variable=self.dec_try_wam)
        cb_tw.grid(row=0, column=0, sticky="w")
        self._tr(lambda s, w=cb_tw: w.configure(text=s), "gui.try_wam")
        self.dec_try_syncseal = tk.BooleanVar(value=False)
        cb_ts = ttk.Checkbutton(ai, variable=self.dec_try_syncseal)
        cb_ts.grid(row=0, column=1, sticky="w", padx=(16, 0))
        self._tr(lambda s, w=cb_ts: w.configure(text=s), "gui.try_syncseal")

        self._mk_label(tb, "gui.decoded_message", row=5, column=0, sticky="nw", pady=(10, 4))
        self.dec_out = scrolledtext.ScrolledText(tb, height=8, wrap="word", font=("Segoe UI", 10))
        self.dec_out.grid(row=5, column=1, columnspan=2, sticky="nsew", padx=6, pady=(10, 4))
        tb.rowconfigure(5, weight=1)

        bottom = ttk.Frame(tb)
        bottom.grid(row=6, column=0, columnspan=3, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.dec_info = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.dec_info.grid(row=0, column=0, sticky="w")
        self.dec_preview = ttk.Label(bottom)
        self.dec_preview.grid(row=0, column=1, sticky="e", padx=6)
        self._mk_button(bottom, "gui.copy_clipboard", self._copy_decoded,
                        row=1, column=0, sticky="w", pady=6)

        vf = ttk.LabelFrame(tb, padding=8)
        vf.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        vf.columnconfigure(1, weight=1)
        self._tr(lambda s, w=vf: w.configure(text=s), "gui.visible_verify_frame")
        self._mk_label(vf, "gui.visible_expected", row=0, column=0, sticky="w")
        self.dec_visible = tk.StringVar()
        ttk.Entry(vf, textvariable=self.dec_visible).grid(row=0, column=1, sticky="ew", padx=6)
        self.dec_verify_btn = self._mk_button(vf, "gui.verify_btn", self._do_verify_visible,
                                              row=0, column=2)
        self.dec_visible_info = ttk.Label(vf, text="", style="Hint.TLabel")
        self.dec_visible_info.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    # ------------------------------------------------------------- pickers
    def _pick_encode_input(self):
        path = filedialog.askopenfilename(filetypes=LOSSLESS_EXT)
        if not path:
            return
        self.enc_input.set(path)
        if not self.enc_output.get():
            base, _ = os.path.splitext(path)
            self.enc_output.set(base + "_stashpix.png")
        self._show_preview(path, self.enc_preview, "enc")
        self._recalc_max_copies()

    def _pick_encode_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("BMP", "*.bmp"), ("TIFF", "*.tif *.tiff")])
        if path:
            self.enc_output.set(path)

    def _pick_decode_input(self):
        path = filedialog.askopenfilename(filetypes=DECODE_EXT)
        if not path:
            return
        self.dec_input.set(path)
        self._show_preview(path, self.dec_preview, "dec")

    def _pick_decode_reference(self):
        path = filedialog.askopenfilename(filetypes=DECODE_EXT)
        if path:
            self.dec_ref.set(path)

    def _show_preview(self, path, label, tag):
        try:
            img = Image.open(path)
            img.thumbnail((120, 120))
            photo = ImageTk.PhotoImage(img)
            self._preview_refs[tag] = photo
            label.configure(image=photo)
        except Exception:
            label.configure(image="")
            self._preview_refs.pop(tag, None)

    # ---------------------------------------------------- capacity helpers
    def _compute_max_copies(self):
        path = self.enc_input.get()
        if not path or not os.path.exists(path):
            return None
        try:
            with Image.open(path) as img:
                w, h = img.size
        except Exception:
            return None
        cap = w * h * 3
        out = {"w": w, "h": h, "cap": cap, "max": None}
        msg = self.enc_msg.get("1.0", "end-1c")
        try:
            nsym = int(self.enc_nsym.get())
        except (tk.TclError, ValueError):
            nsym = None
        if msg and nsym and 1 <= nsym <= 254:
            try:
                L = len(RSCodec(nsym).encode(msg.encode("utf-8"))) * 8
                header = HEADER_ENC_BITS * header_repeats(cap)
                mx = (cap - header) // L if L > 0 else 0
                out["max"] = max(0, min(255, mx))
            except Exception:
                pass
        return out

    def _recalc_max_copies(self):
        info = self._compute_max_copies()
        if not info:
            self.enc_cap.configure(text="")
            return
        txt = t("gui.cap.image", w=info["w"], h=info["h"], cap=info["cap"])
        if info["max"] is not None:
            self._max_copies = max(1, info["max"])
            self.enc_copies_spin.configure(to=self._max_copies)
            if info["max"] == 0:
                txt += t("gui.cap.nofit")
            else:
                txt += t("gui.cap.max", nsym=self.enc_nsym.get(), max=info["max"])
            try:
                if int(self.enc_copies.get()) > self._max_copies:
                    self.enc_copies.set(self._max_copies)
            except (tk.TclError, ValueError):
                pass
        else:
            txt += t("gui.cap.needmsg")
        self.enc_cap.configure(text=txt)

    def _set_max_copies(self):
        self._recalc_max_copies()
        if self._max_copies >= 1:
            self.enc_copies.set(self._max_copies)

    # -------------------------------------------------------------- encode
    def _do_encode(self):
        inp = self.enc_input.get().strip()
        out = self.enc_output.get().strip()
        msg = self.enc_msg.get("1.0", "end-1c")
        if not inp or not os.path.exists(inp):
            return self._error("gui.err.pick_input")
        if not out:
            return self._error("gui.err.pick_output")
        if not msg:
            return self._error("gui.err.empty_message")
        key = self.enc_key.get() or None
        try:
            nsym = int(self.enc_nsym.get())
            copies = int(self.enc_copies.get())
        except (tk.TclError, ValueError):
            return self._error("gui.err.int_fields")
        if not (1 <= nsym <= 254):
            return self._error("gui.err.nsym_range")
        if not (1 <= copies <= 255):
            return self._error("gui.err.copies_range")
        try:
            strength = float(self.enc_strength.get())
        except (tk.TclError, ValueError):
            return self._error("gui.err.strength_number")
        visible = self.enc_visible.get().strip() or None

        config = EmbedConfig(key=key, lsb_nsym=nsym, lsb_copies=copies,
                             lsb_self_verify=self.enc_verify.get(),
                             robust_strength=strength, visible_text=visible,
                             enable_wam=self.enc_wam.get(),
                             enable_syncseal=self.enc_syncseal.get())
        self._busy(True, "gui.status.encoding")

        def work():
            try:
                res = self.engine.embed_file(inp, msg, out, config)
                self._result_q.put(("encode_ok", (res.output_path, res.robust_id)))
            except Exception as e:  # noqa: BLE001
                self._result_q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # -------------------------------------------------------------- decode
    def _do_decode(self):
        inp = self.dec_input.get().strip()
        if not inp or not os.path.exists(inp):
            return self._error("gui.err.pick_image")
        key = self.dec_key.get() or None
        ref = self.dec_ref.get().strip()
        if ref and not os.path.exists(ref):
            return self._error("gui.err.pick_image")
        try:
            strength = float(self.enc_strength.get())
        except (tk.TclError, ValueError):
            strength = DEFAULT_STRENGTH
        self._busy(True, "gui.status.decoding")
        self.dec_out.delete("1.0", "end")

        def work():
            try:
                config = ExtractConfig(key=key, robust_strength=strength,
                                       try_wam=self.dec_try_wam.get(),
                                       try_syncseal=self.dec_try_syncseal.get())
                if ref:
                    text, info = self.engine.extract_geo_file(inp, ref, config)
                else:
                    text, info = self.engine.extract_file(inp, config)
                self._result_q.put(("decode_ok", (text, info)))
            except Exception as e:  # noqa: BLE001
                self._result_q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _do_verify_visible(self):
        inp = self.dec_input.get().strip()
        text = self.dec_visible.get().strip()
        if not inp or not os.path.exists(inp):
            return self._error("gui.err.pick_image")
        if not text:
            return self._error("gui.err.expected_text")
        key = self.dec_key.get() or None
        self._busy(True, "gui.status.verifying")
        self.dec_visible_info.configure(text="")

        def work():
            try:
                present, score, _ = self.engine.verify_visible_file(
                    inp, VerifyConfig(text=text, key=key))
                self._result_q.put(("verify_ok", (present, score)))
            except Exception as e:  # noqa: BLE001
                self._result_q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _copy_decoded(self):
        text = self.dec_out.get("1.0", "end-1c")
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status.set(t("gui.status.clipboard"))

    # ------------------------------------------------------- state helpers
    def _error(self, key):
        messagebox.showerror(t("gui.msg.error"), t(key))

    def _busy(self, on, status_key=None):
        state = "disabled" if on else "normal"
        self.enc_btn.configure(state=state)
        self.dec_btn.configure(state=state)
        if hasattr(self, "dec_verify_btn"):
            self.dec_verify_btn.configure(state=state)
        if on:
            self.progress.start(12)
            if status_key:
                self.status.set(t(status_key))
        else:
            self.progress.stop()

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._result_q.get_nowait()
                self._busy(False)
                if kind == "encode_ok":
                    saved, id_hex = payload
                    self.status.set(t("gui.status.saved", path=saved))
                    messagebox.showinfo(t("gui.msg.success"),
                                        t("gui.msg.encode_ok", path=saved, id=id_hex))
                elif kind == "decode_ok":
                    self._show_decoded(*payload)
                elif kind == "verify_ok":
                    self._show_verify(*payload)
                elif kind == "error":
                    self.status.set(t("gui.status.error"))
                    messagebox.showerror(t("gui.msg.error"), payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _show_decoded(self, text, info):
        self.dec_out.delete("1.0", "end")
        if text is None:
            self.dec_info.configure(text=t("cli.extract.none"))
            self.status.set(t("gui.status.no_message"))
            return
        self.dec_out.insert("1.0", text)
        layer = info.get("layer", "?")
        detail = ""
        if info.get("lsb_info"):
            li = info["lsb_info"]
            detail = t("gui.info.lsb", source=li["recovery_source"],
                       copies=li["copies_total"], errors=li["rs_errors_corrected"])
        elif info.get("robust_info") and info["robust_info"].get("id"):
            detail = t("gui.info.id", id=info["robust_info"]["id"])
        self.dec_info.configure(text=f"{t('cli.extract.layer', layer=layer)}{detail}")
        self.status.set(t("gui.status.decoded"))

    def _show_verify(self, present, score):
        thr = DEFAULT_VISIBLE_THRESHOLD
        if present:
            self.dec_visible_info.configure(text=t("gui.visible.present", score=score, threshold=thr))
            self.status.set(t("gui.status.visible_present"))
        else:
            self.dec_visible_info.configure(text=t("gui.visible.absent", score=score, threshold=thr))
            self.status.set(t("gui.status.visible_absent"))


def main():
    app = StegoGUI()
    if not app.show_eula_modal():
        app.destroy()
        return
    app.mainloop()


if __name__ == "__main__":
    main()
