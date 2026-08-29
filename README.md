# Apple Rabatt

Eine inoffizielle, private Preisrechner-Web-App für Apple-Produkte. Sie liest öffentliche Apple-DE-Produktseiten und öffentliche ZPÜ-Tarife, speichert Preisstände im Repository und berechnet daraus Rabattpreise.

## Automatik

Der Workflow `.github/workflows/update-prices.yml` läuft regelmäßig und kann zusätzlich manuell gestartet werden. `update_prices.py` aktualisiert `current.json`, `history-summary.json` und archiviert Preisstände unter `price-history/`.

## GitHub Pages

Repository → Settings → Pages → Source: **GitHub Actions**.

Repository → Settings → Actions → General → Workflow permissions: **Read and write permissions**.

## Hinweis

Nicht von Apple betrieben oder unterstützt. Produktnamen und Abbildungen gehören den jeweiligen Rechteinhabern. Preise können sich ändern; maßgeblich ist der Apple Store beim Kauf.
