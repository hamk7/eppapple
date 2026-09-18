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


## Paketstand 2026-09-14
- Zubehörbilder visuell überarbeitet (weiße Motive auf hellem Hintergrund, dunkle/farbige Motive freigestellt).
- Produktbilder in Karten/Details leicht herausgezoomt.
- Neue Vorbestellprodukte ergänzt, inkl. AirPods 5.
- Aktuelle Seed-Daten auf Basis offizieller Apple-Store-Preise aus September 2026.


## V6 – Preis-Audit 14.09.2026
- Stale EPP-Overrides werden nur noch verwendet, wenn `eppBaseGross` exakt zum aktuellen Listenpreis passt.
- Preisverlauf enthält Snapshots vom 29.08., 13.09. und 14.09.2026.
- Bilder der neuen Produktgenerationen sind versioniert; Service-Worker Cache wurde erhöht.
- Zubehörbilder wurden auf unbeschnittene Originale zurückgesetzt; weiße Produkte bleiben auf neutralem hellem Bildfeld.
- Vollständiger Audit in `price-audit-2026-09-14.csv`.


## V7 – 18.09.2026
- Produktbilder neu zentriert und ohne transparenten Leerraum normalisiert.
- Service-Worker-Cache auf V7 gesetzt, damit iOS die neuen Bilder tatsächlich lädt.
- Zubehör-Crawler auf alle offiziellen Kategorien plus Filterseiten erweitert.
- Zubehör-Vollständigkeitsprüfung integriert; Details in `ACCESSORY-AUDIT-2026-09-18.md`.
- Historische Preisdateien bleiben unverändert erhalten.
