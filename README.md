# Preisfinder – iPad-Upload-Version

Diese Variante ist absichtlich **flach aufgebaut**: Alle normalen Dateien liegen in einem Ordner, damit sie auf dem iPad über **Add file → Upload files → choose your files** hochgeladen werden können. Nur `update-prices.yml` muss anschließend in GitHub unter `.github/workflows/` abgelegt werden. Der Ordner `price-history/` wird bei der ersten automatischen Aktualisierung selbst erzeugt.

---

# Preisfinder für Apple Geräte

Eine inoffizielle, mobile Web-App für GitHub Pages. Sie liest öffentliche Apple-DE-Listenpreise und offizielle ZPÜ-Geräteabgaben, berechnet daraus den beobachteten Rabattpreis und archiviert alte Preisstände.

## Empfohlene Veröffentlichung

Für die **automatischen Preisupdates** sollte GitHub Pages über **GitHub Actions** veröffentlicht werden:

1. Alle Dateien aus diesem Ordner in den **Root** deines Repositorys hochladen.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions** wählen.
3. Danach unter **Actions** den Workflow **„Preise aktualisieren und Webseite veröffentlichen“** einmal manuell mit **Run workflow** starten.
4. Nach dem ersten erfolgreichen Lauf erscheint die öffentliche Pages-Adresse.

`main / (root) / Deploy from a branch` ist für eine normale statische Seite grundsätzlich korrekt. Für dieses Projekt ist **Source: GitHub Actions** aber besser, weil derselbe Workflow die Preise aktualisiert und die neue Version unmittelbar veröffentlicht.

Die README darf bleiben; sie stört die Webseite nicht.

## Automatische Updates

`.github/workflows/update-prices.yml` läuft stündlich (Minute 17), bei jedem manuellen Push auf `main` und auf Wunsch per **Run workflow**.

Der Workflow:

- liest öffentliche Apple-Store-DE-Seiten,
- liest die offiziellen ZPÜ-Tarifseiten,
- aktualisiert bekannte Produktpreise,
- versucht neue Produktfamilien auf den Apple-Übersichtsseiten automatisch zu erkennen,
- speichert vor Preisänderungen einen Snapshot,
- legt zusätzlich täglich einen Snapshot in `data/history/` ab,
- pflegt `data/history-summary.json` für Vorgängervergleiche,
- veröffentlicht anschließend die aktuelle Webseite selbst über GitHub Pages.

Damit werden bei laufendem Repository auch Preisstände vom 1., 8., 9. September usw. automatisch archiviert. Die Dateien werden vom Projekt nicht automatisch gelöscht.

## Rabattlogik

1. Bruttopreis / 1,19 = Nettopreis
2. Geräteabgabe abziehen
3. Rabatt auf den verbleibenden Nettobetrag anwenden
4. kaufmännisch auf volle Euro runden
5. Geräteabgabe wieder addieren
6. 19 % MwSt. aufschlagen
7. auf Cent runden

Standardmäßig zeigt die Oberfläche **17 %**. Der **27-%-Modus** befindet sich nur ganz unten in den Einstellungen.

## Hinweise

- Die Seite ist inoffiziell und nicht mit Apple verbunden.
- Für die Preisberechnung ist keine Anmeldung bei einer EPP-Seite nötig.
- Apple kann die Struktur seiner Store-Seiten jederzeit ändern. Der Scraper ist deshalb „best effort“: Bei einem Parserfehler bleiben die zuletzt gespeicherten Preise erhalten, bis der Parser angepasst ist.
- Geräteabgaben werden aus den öffentlichen ZPÜ-Seiten aktualisiert. Ausgangswerte: Mobiltelefone 5,00 €, Tablets 7,00 €, Verbraucher-PCs 10,55 €, Smartwatches 1,20 € (Gesamtvertragssätze).
