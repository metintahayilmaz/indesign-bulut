// InDesign Bulut — Arşiv dönüştürücü (ExtendScript)
// Seçilen klasördeki (alt klasörler dahil) tüm .indd dosyalarını yanlarına .idml olarak kaydeder.
// Ardından:  python3 agent.py upload --server ... --token ... <klasör>   ile buluta toplu yükleyin.
//
// Çalıştırma: Pencere > Yardımcı Programlar > Script'ler panelinden çift tıklayın
// (dosyayı "Kullanıcı" script klasörüne kopyaladıktan sonra).

(function () {
    var root = Folder.selectDialog("IDML'e dönüştürülecek .indd dosyalarının klasörünü seçin");
    if (!root) return;

    var files = [];
    (function collect(folder) {
        var items = folder.getFiles();
        for (var i = 0; i < items.length; i++) {
            if (items[i] instanceof Folder) collect(items[i]);
            else if (/\.indd$/i.test(items[i].name)) files.push(items[i]);
        }
    })(root);

    if (!files.length) { alert("Bu klasörde .indd dosyası yok."); return; }
    if (!confirm(files.length + " dosya IDML'e dönüştürülecek. Devam edilsin mi?")) return;

    var oldLevel = app.scriptPreferences.userInteractionLevel;
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    var ok = 0, skipped = 0, errors = [];
    for (var i = 0; i < files.length; i++) {
        var target = new File(files[i].fsName.replace(/\.indd$/i, ".idml"));
        if (target.exists && target.modified >= files[i].modified) { skipped++; continue; }
        var doc = null;
        try {
            doc = app.open(files[i], false);
            doc.exportFile(ExportFormat.INDESIGN_MARKUP, target, false);
            ok++;
        } catch (e) {
            errors.push(files[i].name + ": " + e.message);
        } finally {
            try { if (doc) doc.close(SaveOptions.NO); } catch (e2) {}
        }
    }
    app.scriptPreferences.userInteractionLevel = oldLevel;
    alert("Bitti.\nDönüştürülen: " + ok + "\nZaten güncel: " + skipped + "\nHata: " + errors.length +
          (errors.length ? "\n\n" + errors.slice(0, 10).join("\n") : ""));
})();
