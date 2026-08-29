# Apple Rabatt – Preisrechner

Private, inoffizielle GitHub-Pages-Web-App zur Berechnung und zum Vergleich von Apple-EPP-Referenzpreisen.

## Upload auf dem iPad

1. Alle normalen Dateien aus dem iPad-Upload-Paket in die **oberste Ebene** des Repositorys laden und vorhandene Dateien ersetzen.
2. `update-prices.yml` **nicht** in die oberste Ebene legen, sondern in `.github/workflows/` hochladen und die dortige alte Datei ersetzen.
3. Unter **Settings → Pages → Source** muss **GitHub Actions** gewählt sein.
4. Unter **Settings → Actions → General → Workflow permissions** muss **Read and write permissions** aktiv sein.
5. Unter **Actions** den Workflow einmal manuell mit **Run workflow** starten, falls er nicht automatisch startet.

Die Web-App verwendet die verifizierten EPP-Referenzwerte als Startpunkt. Der Workflow prüft öffentliche Apple-Store-Seiten und ZPÜ-Abgaben, erweitert Konfigurationen und speichert Preisstände in `price-history/`.
