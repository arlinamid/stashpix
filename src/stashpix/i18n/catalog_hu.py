"""Hungarian message catalog."""

CATALOG = {
    # ------------------------------------------------------------------ hibák
    "error.generic": "Váratlan hiba történt.",
    "error.lossy_format": (
        "[Formátum-ellenőrzés] A(z) '{path}' {role} fájl formátuma '{fmt}', ami "
        "VESZTESÉGES, és tönkretenné a rejtett adatot. Használj PNG, BMP vagy TIFF formátumot."
    ),
    "error.lossy_ext": (
        "[Formátum-ellenőrzés] A(z) '{path}' kiterjesztése JPEG-et jelez (veszteséges). "
        "Mentsd/nyisd meg PNG-ként."
    ),
    "error.capacity": (
        "[Kapacitás-ellenőrzés] Szükséges {needed} bit, elérhető {available}. "
        "Ennyi másolat nem fér el (max példányszám ehhez az nsym-hez: {max_copies}). "
        "Csökkentsd a copies/nsym értékét, vagy használj nagyobb képet."
    ),
    "error.nsym_range": "Az nsym 1 és 254 közötti legyen.",
    "error.copies_range": "A példányszám 1 és 255 közötti legyen.",
    "error.decode_header": (
        "[Dekódolási hiba] A fejléc nem olvasható — rossz kulcs, vagy nincs rejtett adat."
    ),
    "error.decode_params": (
        "[Dekódolási hiba] Sérült fejléc (érvénytelen paraméterek) — rossz kulcs, "
        "vagy a kép túlságosan megsérült."
    ),
    "error.decode_rs": (
        "[Dekódolási hiba] A Reed-Solomon dekódolás sem a szavazott, sem az egyedi "
        "másolatokból nem sikerült — a kép túl sérült, vagy rossz a kulcs."
    ),
    "error.decode_utf8": (
        "[Dekódolási hiba] A helyreállított bájtok nem érvényes UTF-8 szöveget adnak "
        "({detail}) — valószínűleg rossz kulcs."
    ),
    "error.self_verify_read": "[Önjavító ellenőrzés] Visszaolvasás sikertelen: {detail}",
    "error.self_verify_mismatch": (
        "[Önjavító ellenőrzés] A mentés utáni dekódolás NEM egyezik az eredeti "
        "üzenettel — a kimeneti fájl nem megbízható."
    ),
    "error.dependency_cv2": (
        "A geometriai szinkronhoz OpenCV kell: pip install opencv-python"
    ),
    "error.image_open": "A(z) '{path}' kép nem nyitható meg: {detail}",
    "error.no_message": "Nincs megadva üzenet.",

    # ------------------------------------------------------------- réteg-nevek
    "layer.lsb.name": "LSB (teljes üzenet, veszteségmentes)",
    "layer.robust.name": "robusztus ID + registry",
    "layer.visible.name": "látható vízjel",
    "layer.geo_tps.name": "morph szinkron (SIFT + TPS + flow) + registry",
    "layer.none": "egyik réteg sem adott vissza üzenetet",

    # -------------------------------------------------------------------- CLI
    "cli.description": (
        "Több rétegű szteganográfia — LSB + robusztus DCT-vízjel + látható vízjel, "
        "fokozatos leépüléssel."
    ),
    "cli.help.lang": "A felület nyelve (en/hu).",
    "cli.embed.help": "Üzenet beágyazása (LSB + robusztus vízjel, opcionális látható).",
    "cli.extract.help": "Üzenet kiolvasása (előbb LSB, majd robusztus ID + registry).",
    "cli.verify_visible.help": "Látható vízjel ellenőrzése.",
    "cli.gui.help": "A desktop GUI indítása.",
    "cli.serve.help": "A REST API / dashboard szerver indítása.",
    "cli.arg.image": "Bemeneti kép (PNG/BMP/TIFF).",
    "cli.arg.image_any": "A vizsgálandó kép (PNG/BMP/TIFF/JPEG).",
    "cli.arg.output": "Kimeneti fájl útvonala.",
    "cli.arg.message": "Az elrejtendő üzenet (szöveg).",
    "cli.arg.message_file": "Az elrejtendő üzenet szöveges fájlból.",
    "cli.arg.key": "Kulcs/jelszó a szétszóráshoz (ugyanaz kell dekódoláshoz).",
    "cli.arg.nsym": "Reed-Solomon ECC bájt / 255 bájtos blokk (alap: 64).",
    "cli.arg.copies": "Redundáns LSB-másolatok száma (alap: 3).",
    "cli.arg.strength": "JND vízjel-erősség (method=jnd).",
    "cli.arg.method": "Vízjel módszer: jnd vagy qim (kiolvasásnál alap: auto).",
    "cli.arg.q": "Fix QIM-lépésköz (method=qim).",
    "cli.arg.visible_text": "Opcionális látható vízjel szövege (4. réteg).",
    "cli.arg.visible_opacity": "Látható vízjel átlátszatlansága (0..1).",
    "cli.arg.reference": "Regisztrált (enkódolt) referencia-kép a geo-szinkronhoz.",
    "cli.arg.output_file": "Ide írja a kiolvasott üzenetet (alap: stdout).",
    "cli.arg.show_info": "Diagnosztikai infó kiírása.",
    "cli.arg.host": "Kiszolgáló cím (alap: 127.0.0.1).",
    "cli.arg.port": "Kiszolgáló port (alap: 8000).",
    "cli.embed.done": "Kombinált beágyazás kész: {path}",
    "cli.embed.robust_id": "  - robusztus réteg ID: {id} (method={method})",
    "cli.embed.lsb": "  - LSB réteg: nsym={nsym}, copies={copies}",
    "cli.embed.visible": "  - látható vízjel: {text!r} (opacity={opacity})",
    "cli.extract.header": "--- Kiolvasott üzenet ---",
    "cli.extract.lsb": "[LSB réteg] Üzenet visszanyerve: {message!r}",
    "cli.extract.robust": "[Robusztus réteg] LSB elveszett; ID={id} -> registry -> {message!r}",
    "cli.extract.none": (
        "Egyik réteg sem adott vissza üzenetet (rossz kulcs, vagy a kép túl sérült / "
        "AI-újragenerált). Ha a kép el lett forgatva, másik képbe vágva vagy részben "
        "kitakarva, próbáld: stashpix extract-geo -i <kép> -r <eredeti> -k <kulcs>"
    ),
    "cli.extract.layer": "réteg: {layer}",
    "cli.extract.saved": "Üzenet elmentve: {path}",
    "cli.verify.present": "Látható vízjel: JELEN VAN (NCC-csúcs={score:.4f}, küszöb={threshold})",
    "cli.verify.absent": (
        "Látható vízjel: nincs (NCC-csúcs={score:.4f}, küszöb={threshold}) — "
        "rossz szöveg/kulcs, hiányzik, vagy erős crop."
    ),
    "cli.error": "HIBA: {detail}",
    "cli.serve.starting": "Szerver indul: http://{host}:{port} (web UI: /, kutatás: /research, API dok: /docs)",
    "cli.serve.need_api": (
        "Az API-hoz extra csomagok kellenek: pip install \"stashpix[api]\" "
        "(vagy fastapi uvicorn python-multipart)."
    ),

    # -------------------------------------------------------------------- GUI
    "gui.title": "Szteganográfia — több rétegű (LSB + robusztus DCT + látható)",
    "gui.tab.encode": "  🔒 Elrejtés  ",
    "gui.tab.decode": "  🔓 Kiolvasás  ",
    "gui.language": "Nyelv:",
    "gui.about": "Névjegy",
    "gui.about.title": "A stashpix névjegye",
    "gui.about.body": (
        "stashpix v{version}\n"
        "Több rétegű kép-szteganográfia — LSB + robusztus DCT + látható vízjel.\n\n"
        "Szerző: Rózsavölgyi János\n"
        "GitHub: https://github.com/arlinamid\n\n"
        "Licenc: PolyForm Noncommercial 1.0.0\n"
        "Személyes / nem kereskedelmi célra ingyenes; kereskedelmi használathoz jóváhagyás kell.\n"
        "A kódolt média kereskedelmi terjesztéséhez (pl. online újság)\n"
        "kereskedelmi licenc szükséges."
    ),
    "gui.about.visit": "GitHub megnyitása",
    "gui.input_image": "Bemeneti kép:",
    "gui.output_file": "Kimeneti fájl:",
    "gui.browse": "Tallózás…",
    "gui.save_as": "Mentés mint…",
    "gui.key": "Kulcs (jelszó):",
    "gui.rs_ecc": "RS ECC (nsym):",
    "gui.copies": "Példányszám:",
    "gui.max": "Max",
    "gui.self_verify": "Önjavító ellenőrzés",
    "gui.strength": "Vízjel erősség:",
    "gui.visible_text": "Látható vízjel (opcionális):",
    "gui.encode_hint": (
        "Mindkét láthatatlan réteg beágyazódik. LSB (nsym/copies) = teljes üzenet, "
        "crop/átfestés-tűrő. Robusztus DCT-vízjel = ID a registryhez, JPEG/resize-tűrő. "
        "Az erősség JND-egységben mért (perceptuálisan adaptív): ~1 a láthatóság határa, "
        "nagyobb = robusztusabb + láthatóbb. A 'Látható vízjel' mező kitöltve egy emberi "
        "szemmel is látható, átlós bélyegzőt is rárak (4. réteg)."
    ),
    "gui.message": "Rejtendő üzenet:",
    "gui.encode_btn": "Üzenet elrejtése",
    "gui.stashpix_image": "Sztego-kép:",
    "gui.reference_image": "Referencia (opcionális):",
    "gui.reference_hint": "Gyanús/módosított képhez (elforgatott, levágott, másik képbe "
                          "illesztett) válaszd ki itt az eredetit az újraigazításhoz.",
    "gui.decoded_message": "Kiolvasott üzenet:",
    "gui.decode_btn": "Üzenet kiolvasása",
    "gui.copy_clipboard": "Másolás vágólapra",
    "gui.visible_verify_frame": "Látható vízjel ellenőrzése (4. réteg)",
    "gui.visible_expected": "Várt szöveg:",
    "gui.verify_btn": "Ellenőrzés",
    "gui.status.ready": "Kész.",
    "gui.status.encoding": "Kombinált beágyazás… (DCT-vízjel + LSB szétszórás, nagy képnél pár másodperc)",
    "gui.status.decoding": "Kiolvasás folyamatban…",
    "gui.status.verifying": "Látható vízjel ellenőrzése…",
    "gui.status.saved": "Kész — mentve: {path}",
    "gui.status.decoded": "Kész — üzenet kiolvasva.",
    "gui.status.no_message": "Nincs kiolvasható üzenet.",
    "gui.status.visible_present": "Látható vízjel: jelen.",
    "gui.status.visible_absent": "Látható vízjel: nincs egyezés.",
    "gui.status.clipboard": "Üzenet a vágólapra másolva.",
    "gui.status.error": "Hiba.",
    "gui.msg.error": "Hiba",
    "gui.msg.success": "Siker",
    "gui.msg.encode_ok": (
        "Az üzenet elrejtve minden rétegben.\n\nMentett fájl:\n{path}\n\n"
        "Robusztus réteg ID (registry):\n{id}"
    ),
    "gui.err.pick_input": "Válassz érvényes bemeneti képet.",
    "gui.err.pick_output": "Adj meg kimeneti fájlt.",
    "gui.err.empty_message": "Az üzenet üres.",
    "gui.err.int_fields": "Az nsym és a példányszám egész szám legyen.",
    "gui.err.nsym_range": "Az nsym 1 és 254 közötti legyen.",
    "gui.err.copies_range": "A példányszám 1 és 255 közötti legyen.",
    "gui.err.strength_number": "A vízjel erősség szám legyen.",
    "gui.err.pick_image": "Válassz érvényes képet.",
    "gui.err.expected_text": "Add meg a várt látható vízjel szövegét.",
    "gui.cap.image": "Kép: {w}×{h}px — kapacitás {cap} bit",
    "gui.cap.max": " • max példányszám ehhez az üzenethez (nsym={nsym}): {max}",
    "gui.cap.nofit": " • az üzenet így NEM fér el (növeld a képet / csökkentsd az nsym-et)",
    "gui.cap.needmsg": " • adj meg üzenetet a max példányszámhoz",
    "gui.info.lsb": " • forrás: {source}, {copies} másolat, {errors} RS-hiba javítva",
    "gui.info.id": " • ID: {id}",
    "gui.visible.present": "OK — látható vízjel JELEN VAN (NCC={score:.3f} >= {threshold})",
    "gui.visible.absent": (
        "Nincs egyezés (NCC={score:.3f} < {threshold}) — rossz szöveg/kulcs, hiányzik, vagy erős crop."
    ),

    # -------------------------------------------------------------------- API
    "api.title": "stashpix API",
    "api.embed.ok": "Az üzenet sikeresen beágyazva.",
    "api.extract.ok": "Üzenet kiolvasva.",
    "api.extract.none": "Egyik réteg sem adott vissza üzenetet.",
    "api.verify.ok": "Az ellenőrzés kész.",
    "api.err.no_file": "Nincs feltöltött képfájl.",
    "api.err.no_message": "Nincs megadva üzenet.",

    # ----------------------------------------------------------------- web UI
    "web.title": "stashpix",
    "web.subtitle": "Több rétegű szteganográfia — LSB + robusztus DCT-vízjel + látható vízjel",
    "web.status.online": "elérhető",
    "web.status.offline": "nem elérhető",
    "web.label.version": "verzió",
    "web.label.registry": "registry bejegyzés",
    "web.label.geo": "geo (SIFT)",
    "web.language": "Nyelv",
    "web.tab.embed": "Beágyazás",
    "web.tab.extract": "Kiolvasás",
    "web.tab.verify": "Látható vízjel",
    "web.tab.registry": "Registry",
    "web.tab.about": "Névjegy",
    "web.field.cover": "Hordozó kép",
    "web.field.image": "Kép",
    "web.field.message": "Üzenet",
    "web.field.key": "Kulcs (jelszó)",
    "web.field.copies": "LSB példányszám",
    "web.field.nsym": "RS ECC (nsym)",
    "web.field.strength": "Vízjel erősség",
    "web.field.visible": "Látható vízjel szövege (opcionális)",
    "web.field.expected": "Várt látható szöveg",
    "web.field.reference": "Referencia kép (opcionális — gyanús/módosított képhez)",
    "web.field.reference_hint": "Ha a kép elforgatottnak, levágottnak tűnik, vagy másik "
                               "képbe illesztették, add meg ide az eredetit az újraigazításhoz.",
    "web.btn.embed": "Beágyazás és letöltés",
    "web.btn.extract": "Kiolvasás",
    "web.btn.verify": "Ellenőrzés",
    "web.btn.refresh": "Frissítés",
    "web.btn.choose": "Fájl kiválasztása…",
    "web.msg.processing": "Feldolgozás…",
    "web.msg.embed_ok": "Beágyazva. Robusztus ID: {id}",
    "web.msg.download": "Sztego-kép letöltése",
    "web.msg.no_message": "Egyik réteg sem adott vissza üzenetet.",
    "web.msg.layer": "Helyreállító réteg: {layer}",
    "web.msg.present": "JELEN VAN — a látható vízjel egyezik (NCC {score}).",
    "web.msg.absent": "Nincs (NCC {score}) — rossz szöveg/kulcs, hiányzik, vagy erős crop.",
    "web.msg.error": "Hiba",
    "web.registry.title": "Aktuális registry állapot",
    "web.registry.id": "ID",
    "web.registry.message": "Üzenet",
    "web.registry.created": "Létrehozva",
    "web.registry.source": "Forrás",
    "web.registry.output": "Kimenet",
    "web.registry.empty": "A registry üres — előbb ágyazz be valamit.",
    "web.registry.autorefresh": "Auto-frissítés",
    "web.about.body": (
        "Négy réteg fokozatos leépüléssel: az LSB a teljes üzenetet hordozza "
        "(crop/átfestés-tűrő), a robusztus DCT-vízjel egy ID-t hordoz, amit a "
        "registry old fel (JPEG/resize-tűrő), a geometriai szinkron újraigazítja "
        "a transzformált képeket, a látható vízjel pedig emberi szemmel is "
        "olvasható, ellenőrizhető bélyegzőt ad."
    ),
    "web.about.research": "Kutatási dashboard megnyitása",

    # ------------------------------------------------------------------- EULA
    "eula.title": "Licencszerződés — stashpix",
    "eula.intro": (
        "A stashpix v{version} a PolyForm Noncommercial License 1.0.0 alatt áll, "
        "kiegészítve a Kódolt Média záradékkal. Kérjük, olvasd el és fogadd el a "
        "feltételeket a szoftver használata előtt."
    ),
    "eula.terms": (
        "Az elfogadással beleegyezel, hogy:\n"
        "  • A személyes és egyéb NEM KERESKEDELMI használat ingyenes (a "
        "módosítás és továbbadás is, azonos feltételekkel).\n"
        "  • A szoftver KERESKEDELMI használatához külön kereskedelmi licenc "
        "szükséges, amit a szerző csak előzetes írásos jóváhagyással ad.\n"
        "  • KÓDOLT MÉDIA: az ezzel a szoftverrel készült, vízjelet vagy rejtett "
        "adatot hordozó fájlok nem kereskedelmi célra szabadon készíthetők és "
        "megoszthatók, de az ilyen média KERESKEDELMI TERJESZTÉSÉHEZ (pl. online "
        "újság vagy bármely profitorientált kiadó általi közzététel) kereskedelmi "
        "licenc kell.\n"
        "  • A szoftver „AHOGY VAN” alapon, mindenféle garancia nélkül működik.\n"
        "Teljes szöveg: lásd a LICENSE fájlt. Kereskedelmi licenc / kapcsolat: "
        "https://github.com/arlinamid"
    ),
    "eula.accept": "Elfogadom",
    "eula.decline": "Elutasítom",
    "eula.view_full": "Teljes LICENSE megtekintése",
    "eula.prompt": "Elfogadod a feltételeket? [i/N]: ",
    "eula.accepted": "A licencfeltételek elfogadva (v{version}). Rögzítve: {path}.",
    "eula.declined": "A licencfeltételek nem lettek elfogadva — kilépés.",
    "eula.required": (
        "A stashpix használata előtt el kell fogadnod a licencfeltételeket. "
        "Indíts interaktív terminált és válaszolj a kérdésre, add meg a "
        "--accept-license kapcsolót, vagy állítsd be a stashpix_ACCEPT_LICENSE=1 "
        "változót. Teljes szöveg: LICENSE."
    ),
    "eula.status.accepted": "Elfogadva: v{version}, {when} (mód: {method}).",
    "eula.status.not_accepted": "Még nincs elfogadva.",
    "cli.license.help": "Licenc megjelenítése, elfogadási állapot, vagy elfogadás.",
    "cli.arg.accept_license": "A licencfeltételek elfogadása interakció nélkül.",
    "cli.arg.license_status": "Az aktuális elfogadási állapot kiírása, majd kilépés.",
    "cli.arg.license_show": "A teljes LICENSE szöveg kiírása, majd kilépés.",
    "cli.arg.license_reset": "Elfogadás visszaállítása (a feltételek újra megjelennek).",
    "eula.reset.done": "Az elfogadás visszaállítva — a feltételek legközelebb újra megjelennek.",
    "eula.reset.none": "Nincs elfogadási rekord; nincs mit visszaállítani.",
    "cli.license.header": "stashpix licenc állapot",
}
