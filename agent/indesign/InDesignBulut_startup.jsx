// InDesign Bulut — InDesign başlangıç script'i (ExtendScript)
//
// KURULUM: Bu dosyayı InDesign'ın "Startup Scripts" klasörüne kopyalayın ve InDesign'ı yeniden başlatın.
//   macOS  : ~/Library/Preferences/Adobe InDesign/<sürüm>/<dil>/Scripts/Startup Scripts/
//   Windows: %APPDATA%\Adobe\InDesign\<sürüm>\<dil>\Scripts\Startup Scripts\
// (Klasörü bulmak için: Pencere > Yardımcı Programlar > Script'ler > "Kullanıcı" klasörüne sağ tık > Bul / Explorer'da göster)
//
// Script, Belgeler/InDesignBulut/inbox klasörünü birkaç saniyede bir kontrol eder. agent.py'nin bıraktığı
// her <id>.json talimatı için dosyayı açar, PDF veya IDML olarak outbox'a aktarır ve kapatır.
#targetengine "indesignbulut"

var BULUT = BULUT || {};
BULUT.hot = Folder.myDocuments.fsName + "/InDesignBulut";
BULUT.busy = false;

BULUT.readJSON = function (file) {
    file.encoding = "UTF-8";
    file.open("r");
    var s = file.read();
    file.close();
    return eval("(" + s + ")"); // ExtendScript'te JSON.parse yoktur; dosya kendi ajanımızdan gelir
};

BULUT.writeText = function (file, text) {
    file.encoding = "UTF-8";
    file.open("w");
    file.write(text);
    file.close();
};

BULUT.processJob = function (jobFile) {
    var inbox = jobFile.parent;
    var outbox = new Folder(BULUT.hot + "/outbox");
    var job = BULUT.readJSON(jobFile);
    var doc = null;
    var oldLevel = app.scriptPreferences.userInteractionLevel;
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
