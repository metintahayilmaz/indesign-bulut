// InDesign Bulut — InDesign başlangıç script'i (ExtendScript)
//
// KURULUM: Bu dosyayı InDesign'ın "Startup Scripts" klasörüne kopyalayın ve InDesign'ı yeniden başlatın.
//   macOS  : ~/Library/Preferences/Adobe InDesign/<sürüm>/<dil>/Scripts/Startup Scripts/
//   Windows: %APPDATA%\Adobe\InDesign\<sürüm>\<dil>\Scripts\Startup Scripts\
// (Klasörü bulmak için: Pencere > Yardımcı Programlar > Script'ler > "Kullanıcı" klasörüne sağ tık > Bul / Explorer'da göster)
//
// Script, Belgeler/InDesignBulut/inbox klasörünü birkaç saniyede bir kontrol eder. agent.py'nin bıraktığı
// her <id>.json talimatı için dosyayı açar, PDF veya IDML olarak outbox'a aktarır ve kapatır.
// "layout" işlerinde şablonu açar, layout.json planına göre dergi sayfalarını kurar (bkz. tasarim/SPEC.md).
// SÜRÜM: 2 — script güncellendiğinde InDesign'ı yeniden başlatın.
#targetengine "indesignbulut"

var BULUT = BULUT || {};
BULUT.hot = Folder.myDocuments.fsName + "/InDesignBulut";
BULUT.busy = false;

BULUT.readJSON = function (file) {
    file.encoding = "UTF-8";
    file.open("r");
    var s = file.read();
    file.close();
    // ES3 dizgilerinde U+2028/2029 satır sonu sayılır; eval'den önce kaçışla
    s = s.replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
    return eval("(" + s + ")"); // ExtendScript'te JSON.parse yoktur; dosya kendi ajanımızdan gelir
};

BULUT.writeText = function (file, text) {
    file.encoding = "UTF-8";
    file.open("w");
    file.write(text);
    file.close();
};

// ---------------------------------------------------------------------------
// Tasarım: layout.json planından sayfa kurulumu
// ---------------------------------------------------------------------------
BULUT.toJSON = function (v) {
    if (v === null || v === undefined) return "null";
    var t = typeof v;
    if (t === "number") return isFinite(v) ? String(Math.round(v * 100) / 100) : "null";
    if (t === "boolean") return v ? "true" : "false";
    if (t === "string") {
        return '"' + v.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")
            .replace(/\r/g, "\\r").replace(/\t/g, "\\t").replace(/[\x00-\x1f\u2028\u2029]/g, " ") + '"';
    }
    var parts = [], i, k;
    if (v instanceof Array) {
        for (i = 0; i < v.length; i++) parts.push(BULUT.toJSON(v[i]));
        return "[" + parts.join(",") + "]";
    }
    for (k in v) if (v.hasOwnProperty(k)) parts.push(BULUT.toJSON(String(k)) + ":" + BULUT.toJSON(v[k]));
    return "{" + parts.join(",") + "}";
};

// Stil koleksiyonu -> {ad: stil, "Grup/Ad": stil}
BULUT.styleMap = function (coll) {
    var map = {}, i, st, path, p;
    for (i = 0; i < coll.length; i++) {
        st = coll[i];
        map[st.name] = st;
        path = st.name;
        p = st.parent;
        while (p && p.constructor && /Group$/.test(p.constructor.name)) {
            path = p.name + "/" + path;
            p = p.parent;
        }
        map[path] = st;
    }
    return map;
};

BULUT.findMaster = function (doc, name) {
    for (var i = 0; i < doc.masterSpreads.length; i++) {
        var ms = doc.masterSpreads[i];
        if (ms.name === name || ms.namePrefix === name || ms.baseName === name) return ms;
    }
    return null;
};

// Sayfa geometrisi (mm, yayılım/spread koordinatları). Karşılıklı sayfalarda marginPreferences.left = iç, right = dış.
BULUT.pageGeom = function (doc, page) {
    var b = page.bounds, mp = page.marginPreferences, dp = doc.documentPreferences;
    var side = "single";
    if (dp.facingPages) side = (page.side === PageSideOptions.LEFT_HAND) ? "left" : "right";
    return {
        x0: b[1], y0: b[0], W: b[3] - b[1], H: b[2] - b[0], side: side,
        top: mp.top, bottom: mp.bottom, inside: mp.left, outside: mp.right,
        cols: mp.columnCount, gutter: mp.columnGutter,
        bleed: { top: dp.documentBleedTopOffset, bottom: dp.documentBleedBottomOffset,
                 inside: dp.documentBleedInsideOrLeftOffset, outside: dp.documentBleedOutsideOrRightOffset }
    };
};

// tasarim/spec.py frame_box ile aynı hesap. Dönüş: [y1, x1, y2, x2] spread koordinatları
BULUT.frameBounds = function (g, fr) {
    var ml = (g.side === "left") ? g.outside : g.inside;
    var mr = (g.side === "left") ? g.inside : g.outside;
    var x1, y1, x2, y2;
    if (fr.x !== undefined && fr.y !== undefined && fr.w !== undefined && fr.h !== undefined) {
        x1 = fr.x; y1 = fr.y; x2 = fr.x + fr.w; y2 = fr.y + fr.h;
    } else {
        var n = g.cols || 1, gut = g.gutter || 0;
        var cw = ((g.W - ml - mr) - (n - 1) * gut) / n;
        var col = fr.col || 1, span = fr.span || 1;
        x1 = ml + (col - 1) * (cw + gut);
        x2 = x1 + span * cw + (span - 1) * gut;
        y1 = g.top + (fr.top || 0);
        y2 = (fr.height !== undefined) ? y1 + fr.height : g.H - g.bottom - (fr.bottom || 0);
    }
    var leftIs = (g.side === "left") ? "outside" : "inside";
    var rightIs = (g.side === "left") ? "inside" : "outside";
    var bl = fr.bleed || [];
    for (var i = 0; i < bl.length; i++) {
        if (bl[i] === "top") y1 = -g.bleed.top;
        else if (bl[i] === "bottom") y2 = g.H + g.bleed.bottom;
        else if (bl[i] === leftIs) x1 = -g.bleed[leftIs];
        else if (bl[i] === rightIs) x2 = g.W + g.bleed[rightIs];
    }
    return [g.y0 + y1, g.x0 + x1, g.y0 + y2, g.x0 + x2];
};

// "<c:Stil>metin</c>" işaretli paragraf metnini düz metne ve karakter stili aralıklarına çevirir
BULUT.parseRuns = function (text, offset, runs) {
    var re = /<c:([^>]+)>([\s\S]*?)<\/c>/g, plain = "", last = 0, m;
    while ((m = re.exec(text)) !== null) {
        plain += text.substring(last, m.index);
        var s0 = offset + plain.length;
        plain += m[2];
        runs.push({ start: s0, end: offset + plain.length, style: m[1] });
        last = re.lastIndex;
    }
    plain += text.substring(last);
    return plain.replace(/\r/g, "").replace(/\n/g, "\u2028"); // \n -> satır sonu (paragrafı bölmeden)
};

BULUT.processLayout = function (job) {
    var outdir = new Folder(job.outdir);
    if (!outdir.exists) outdir.create();
    var spec = BULUT.readJSON(new File(job.spec));
    var report = { pages: 0, overset: [], missing: [], low_ppi: [], errors: [], warnings: [], geometry: [] };
    var missingSeen = {};
    function missing(kind, name) {
        if (!missingSeen[kind + name]) { missingSeen[kind + name] = true; report.missing.push(kind + ": " + name); }
    }

    var doc = app.open(new File(job.template), false);
    try {
        var vp = doc.viewPreferences;
        var oldUnits = [vp.horizontalMeasurementUnits, vp.verticalMeasurementUnits, vp.rulerOrigin];
        vp.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
        vp.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
        vp.rulerOrigin = RulerOrigin.SPREAD_ORIGIN;

        var pstyles = BULUT.styleMap(doc.allParagraphStyles);
        var cstyles = BULUT.styleMap(doc.allCharacterStyles);
        var ostyles = BULUT.styleMap(doc.allObjectStyles);

        // Sayfa sayısı ve numaralandırma (çift numara = sol sayfa)
        var n = spec.pages.length, i, j;
        var sec = doc.sections[0];
        sec.continueNumbering = false;
        sec.pageNumberStart = spec.start_page || 1;
        while (doc.pages.length < n) doc.pages.add(LocationOptions.AT_END);
        while (doc.pages.length > n) doc.pages[-1].remove();

        var storyFrames = {};
        for (i = 0; i < n; i++) {
            var pg = spec.pages[i], page = doc.pages[i];
            // Şablon sayfasındaki eski öğeleri temizle (ana sayfa öğeleri etkilenmez)
            for (j = page.pageItems.length - 1; j >= 0; j--) {
                try { page.pageItems[j].locked = false; page.pageItems[j].remove(); } catch (eRm) {}
            }
            if (pg.master) {
                var ms = BULUT.findMaster(doc, pg.master);
                if (ms) page.appliedMaster = ms; else missing("ana sayfa", pg.master);
            }
            // Vinyetler: ana sayfadaki adlandırılmış metin çerçevelerini bu sayfada geçersiz kılıp metnini yaz
            if (pg.master_text) {
                for (var key in pg.master_text) {
                    if (!pg.master_text.hasOwnProperty(key)) continue;
                    var found = false, mitems = page.masterPageItems;
                    for (j = 0; j < mitems.length; j++) {
                        if (mitems[j].name === key && mitems[j].constructor.name === "TextFrame") {
                            var ov = mitems[j].override(page);
                            ov.parentStory.contents = String(pg.master_text[key]);
                            found = true;
                        }
                    }
                    if (!found) report.warnings.push("sayfa " + (i + 1) + ": vinyet çerçevesi bulunamadı: " + key);
                }
            }
            var g = BULUT.pageGeom(doc, page);
            report.geometry.push({ page: page.name, side: g.side, margins: [g.top, g.bottom, g.inside, g.outside],
                                   columns: g.cols, gutter: g.gutter });

            var frames = pg.frames || [];
            for (j = 0; j < frames.length; j++) {
                var fr = frames[j], bounds = BULUT.frameBounds(g, fr), item = null;
                var where = "sayfa " + (i + 1) + ", çerçeve " + (j + 1);
                if (fr.type === "text") {
                    item = page.textFrames.add({ geometricBounds: bounds });
                    if (fr.columns && fr.columns > 1) {
                        item.textFramePreferences.textColumnCount = fr.columns;
                        item.textFramePreferences.textColumnGutter = g.gutter;
                    }
                    if (fr.valign === "center") item.textFramePreferences.verticalJustification = VerticalJustification.CENTER_ALIGN;
                    else if (fr.valign === "bottom") item.textFramePreferences.verticalJustification = VerticalJustification.BOTTOM_ALIGN;
                    if (!storyFrames[fr.story]) storyFrames[fr.story] = [];
                    storyFrames[fr.story].push(item);
                } else if (fr.type === "image") {
                    item = page.rectangles.add({ geometricBounds: bounds });
                    if (!fr.object_style) { item.strokeWeight = 0; }
                    var img = new File(job.assets + "/" + fr.image);
                    if (!img.exists) { missing("görsel", fr.image); }
                    else {
                        try {
                            item.place(img);
                            if (fr.fit === "fit") item.fit(FitOptions.PROPORTIONALLY);
                            else item.fit(FitOptions.FILL_PROPORTIONALLY);
                            item.fit(FitOptions.CENTER_CONTENT);
                            if (item.graphics.length) {
                                var ppi = item.graphics[0].effectivePpi;
                                var minPpi = Math.min(ppi[0], ppi[1]);
                                if (minPpi < 200) report.low_ppi.push(where + ": " + fr.image + " ~" + minPpi + " ppi");
                            }
                        } catch (ePl) { report.errors.push(where + ": görsel yerleştirilemedi (" + fr.image + "): " + ePl.message); }
                    }
                    if (fr.wrap) {
                        var o = (fr.wrap_offset !== undefined) ? fr.wrap_offset : 3;
                        item.textWrapPreferences.textWrapMode = TextWrapModes.BOUNDING_BOX_TEXT_WRAP;
                        item.textWrapPreferences.textWrapOffset = [o, o, o, o];
                    }
                } else if (fr.type === "rect") {
                    item = page.rectangles.add({ geometricBounds: bounds });
                    if (!fr.object_style) item.strokeWeight = 0;
                    if (fr.fill) {
                        var sw = doc.swatches.itemByName(fr.fill);
                        if (sw.isValid) { item.fillColor = sw; if (fr.tint !== undefined) item.fillTint = fr.tint; }
                        else missing("renk", fr.fill);
                    }
                }
                if (item && fr.object_style) {
                    if (ostyles[fr.object_style]) item.applyObjectStyle(ostyles[fr.object_style], true);
                    else missing("nesne stili", fr.object_style);
                }
            }
        }

        // Metinler: aynı hikâyeyi kullanan çerçeveleri sırayla bağla, paragrafları stilleriyle yaz
        var stories = spec.stories || {};
        for (var sid in stories) {
            if (!stories.hasOwnProperty(sid)) continue;
            var list = storyFrames[sid];
            if (!list || !list.length) { report.warnings.push("hikâye çerçevesiz: " + sid); continue; }
            for (j = 1; j < list.length; j++) list[j - 1].nextTextFrame = list[j];
            var story = list[0].parentStory, paras = stories[sid], full = "", runs = [], starts = [];
            for (j = 0; j < paras.length; j++) {
                var plain = BULUT.parseRuns(String(paras[j].text), full.length, runs);
                starts.push(full.length);
                full += plain + (j < paras.length - 1 ? "\r" : "");
            }
            story.contents = full;
            for (j = 0; j < paras.length && j < story.paragraphs.length; j++) {
                var stName = paras[j].style;
                if (!stName) continue;
                if (pstyles[stName]) story.paragraphs[j].applyParagraphStyle(pstyles[stName], true);
                else missing("paragraf stili", stName);
            }
            for (j = 0; j < runs.length; j++) {
                if (runs[j].end <= runs[j].start) continue;
                if (cstyles[runs[j].style]) story.characters.itemByRange(runs[j].start, runs[j].end - 1).appliedCharacterStyle = cstyles[runs[j].style];
                else missing("karakter stili", runs[j].style);
            }
            if (list[list.length - 1].overflows) report.overset.push(sid);
        }

        for (i = 0; i < doc.fonts.length; i++) {
            if (doc.fonts[i].status !== FontStatus.INSTALLED) report.warnings.push("yazı tipi eksik: " + doc.fonts[i].name);
        }
        report.pages = doc.pages.length;

        vp.horizontalMeasurementUnits = oldUnits[0];
        vp.verticalMeasurementUnits = oldUnits[1];
        vp.rulerOrigin = oldUnits[2];

        // Çıktılar: .indd, .idml, PDF, sayfa önizlemeleri (PNG)
        doc.save(new File(outdir.fsName + "/tasarim.indd"));
        doc.exportFile(ExportFormat.INDESIGN_MARKUP, new File(outdir.fsName + "/tasarim.idml"), false);
        var preset = app.pdfExportPresets.itemByName(job.preset || "[High Quality Print]");
        if (!preset.isValid) preset = app.pdfExportPresets[0];
        app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES;
        doc.exportFile(ExportFormat.PDF_TYPE, new File(outdir.fsName + "/tasarim.pdf"), false, preset);
        var png = app.pngExportPreferences;
        png.exportResolution = 100;
        png.pngQuality = PNGQualityEnum.HIGH;
        png.useDocumentBleeds = false;
        png.transparentBackground = false;
        png.pngExportRange = PNGExportRangeEnum.EXPORT_RANGE;
        for (i = 0; i < doc.pages.length; i++) {
            png.pageString = doc.pages[i].name;
            doc.exportFile(ExportFormat.PNG_FORMAT, new File(outdir.fsName + "/sayfa-" + (i + 1) + ".png"), false);
        }
    } finally {
        BULUT.writeText(new File(outdir.fsName + "/rapor.json"), BULUT.toJSON(report));
        try { doc.close(SaveOptions.NO); } catch (eCl) {}
    }
};

BULUT.processJob = function (jobFile) {
    var inbox = jobFile.parent;
    var outbox = new Folder(BULUT.hot + "/outbox");
    var job = BULUT.readJSON(jobFile);
    var doc = null;
    var oldLevel = app.scriptPreferences.userInteractionLevel;
    if (job.kind === "layout") {
        try {
            app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
            BULUT.processLayout(job);
            BULUT.writeText(new File(outbox.fsName + "/" + job.id + ".done"), "ok");
        } catch (eL) {
            BULUT.writeText(new File(outbox.fsName + "/" + job.id + ".error.txt"),
                (eL.message || String(eL)) + (eL.line ? " (satır " + eL.line + ")" : ""));
        } finally {
            app.scriptPreferences.userInteractionLevel = oldLevel;
            jobFile.remove();
        }
        return;
    }
    var part = new File(outbox.fsName + "/" + job.id + ".part");
    try {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
        var src = new File(inbox.fsName + "/" + job.input);
        if (!src.exists) throw new Error("Girdi dosyası bulunamadı: " + job.input);
        doc = app.open(src, false); // pencere açmadan

        if (job.kind === "pdf") {
            var preset = app.pdfExportPresets.itemByName(job.preset);
            if (!preset.isValid) preset = app.pdfExportPresets.itemByName("[High Quality Print]");
            app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES;
            doc.exportFile(ExportFormat.PDF_TYPE, part, false, preset);
        } else if (job.kind === "indd_to_idml") {
            doc.exportFile(ExportFormat.INDESIGN_MARKUP, part, false);
        } else {
            throw new Error("Bilinmeyen iş türü: " + job.kind);
        }
        doc.close(SaveOptions.NO);
        doc = null;
        part.rename(job.output); // ajan yalnızca tamamlanmış dosyayı görür
    } catch (e) {
        try { if (doc) doc.close(SaveOptions.NO); } catch (e2) {}
        if (part.exists) part.remove();
        BULUT.writeText(new File(outbox.fsName + "/" + job.id + ".error.txt"),
            (e.message || String(e)) + (e.line ? " (satır " + e.line + ")" : ""));
    } finally {
        app.scriptPreferences.userInteractionLevel = oldLevel;
        jobFile.remove(); // aynı iş tekrar işlenmesin
    }
};

BULUT.onIdle = function () {
    if (BULUT.busy) return;
    BULUT.busy = true;
    try {
        var inbox = new Folder(BULUT.hot + "/inbox");
        var outbox = new Folder(BULUT.hot + "/outbox");
        if (!inbox.exists) inbox.create();
        if (!outbox.exists) outbox.create();
        var jobs = inbox.getFiles("*.json");
        for (var i = 0; i < jobs.length; i++) BULUT.processJob(jobs[i]);
    } catch (e) {
        $.writeln("InDesignBulut: " + e);
    }
    BULUT.busy = false;
};

(function install() {
    var name = "InDesignBulut";
    var old = app.idleTasks.itemByName(name);
    if (old.isValid) old.remove();
    var task = app.idleTasks.add({ name: name, sleep: 3000 });
    task.addEventListener(IdleEvent.ON_IDLE, BULUT.onIdle, false);
})();
