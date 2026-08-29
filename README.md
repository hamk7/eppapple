# Apple Rabatt – V5

Inoffizielle GitHub-Pages-Web-App zur Berechnung und zum Vergleich von Apple-Rabattpreisen.

## V5

- Darstellung: **System / Hell / Dunkel**, Standard ist **System**.
- Korrigierte Apple-Rundungslogik: rabattierten Nettowert zuerst auf Cent, danach auf volle Euro runden.
- Verifizierte EPP-Referenzwerte bleiben als exakte Overrides erhalten.
- Einkaufstasche und Einstellungen bleiben lokal im Browser gespeichert.
- Preisvergleich wird aus `price-history/` wieder aufgebaut und kann zusätzlich aktuelle Vorgängermodelle vergleichen.
- Zubehör wird über alle öffentlichen Apple-Zubehörkategorien gesucht; fehlende Kartenpreise werden bei einem tiefen Scan über Produktseiten ergänzt.
- Weiße Zubehörbilder werden nicht mehr destruktiv freigestellt; Bildflächen sind bewusst neutral-hell, damit Kabel/Adapter vollständig bleiben.
- Fehler eines einzelnen Apple/ZPÜ-Scrapes verhindern nicht mehr die Veröffentlichung der Webseite.

## Upload auf dem iPad

1. Die normalen V5-Patch-Dateien in die **oberste Ebene** des Repositorys laden und vorhandene Dateien ersetzen.
2. Den Ordner `price-history/` **nicht löschen**.
3. `.github/workflows/update-prices.yml` separat durch die V5-Workflow-Datei ersetzen.
4. **Settings → Pages → Source: GitHub Actions**.
5. **Settings → Actions → General → Workflow permissions: Read and write permissions**.
6. Unter **Actions** den Workflow bei Bedarf einmal mit **Run workflow** starten.

Die Web-App ist eine normale responsive Webseite/PWA und funktioniert auch auf Android, Windows, macOS und Desktop-Browsern. Lokale Einkaufstaschen werden nicht automatisch zwischen Geräten synchronisiert.
