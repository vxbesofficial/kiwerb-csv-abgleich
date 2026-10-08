KIWERB CSV-Abgleich
==================

Ein kleines, lokal ausführbares Arbeitsbeispiel: Zwei CSV-Dateien über einen
gewählten Schlüssel vergleichen und eine nachvollziehbare Prüfliste erzeugen.
Abweichungen und Mehrfachschlüssel bleiben sichtbar; Originaldateien werden
nicht geändert. Der Vergleich bewertet keine fachliche Richtigkeit.

Der Quellcode und die Tests wurden KI-gestützt für KIWERB erstellt. Die
Veröffentlichung übernimmt die KI-Projektassistenz für Ramin Adrian Fenchel.
Alle mitgelieferten Daten sind synthetisch. Es handelt sich um einen technischen
Nachweis mit begrenztem Umfang, keine Kundenreferenz oder Kundenabnahme.

Start mit dem synthetischen Beispiel
-----------------------------------
Vorhandenes Python 3.9 oder neuer und eine lokale Kommandozeile sind erforderlich.
Es werden nur Module der Python-Standardbibliothek verwendet. Das Programm
benötigt und verwendet weder Netzwerkzugang noch API-Schlüssel oder Server.

Im Repository-Ordner ausführen (lauf-01 darf noch nicht existieren):

python3 reconcile.py --a examples/quelle-a-synthetisch.csv --b examples/quelle-b-synthetisch.csv --key Referenz --fields Betrag_EUR --out lauf-01

Bei erfolgreichem Abschluss enthält lauf-01 die Dateien report.json und
result.html. Der JSON-Bericht bewahrt alle Rohwerte und Originalzeilenverweise.
Die HTML-Datei zeigt sie als escaped Text ohne Skripte oder externe Ressourcen.
Ein vorhandener Ausgabeordner wird abgelehnt. Solange UNVOLLSTAENDIG.txt im
Zielordner liegt, ist der Lauf nicht abgeschlossen.

Erwartete Schlüsselgruppen für dieses Beispiel:
  9 Treffer, 2 Feldabweichungen, 2 Nur A, 2 Nur B,
  1 Dublette und 1 Mehrdeutig; insgesamt 17 Gruppen aus je 16 Quellzeilen.

Tests reproduzieren
-------------------

python3 test_acceptance.py

31 automatisierte Blackbox-Tests prüfen unter anderem Rohwerterhalt, Mehrfach-
schlüssel, Fehlermeldungen, Eingabegrenzen und das Nichtüberschreiben bestehender
Dateien. Sie wurden lokal unter macOS ausgeführt. Die Tests untersuchen
HTML-Ausgabetexte; eine gesonderte visuelle Browserprüfung, Kundenbedienprobe
oder Windows-Abnahme ist damit nicht belegt.

Vergleichsregeln und Grenzen
---------------------------
- Genau zwei verschiedene reguläre UTF-8-CSV-Dateien, optional mit BOM.
- Je Quelle höchstens 1.000 Datenzeilen und 10 MiB, 1 bis 10 Vergleichsfelder.
- Standardtrennzeichen Semikolon; --delimiter kann es ausdrücklich ändern.
- Exakter Textvergleich: 001 und 1, 0 und leer sowie 0.00 und 0.0 sind verschieden.
- Keine Summenberechnung, Zahlen-/Datumsnormalisierung, Fuzzy-Zuordnung oder XLSX.
- Mehrfachschlüssel werden nicht gepaart, entfernt oder automatisch korrigiert.
- Dublette bedeutet identische Rohfelder innerhalb jeder mehrfachen Seite;
  daraus folgt weder Gleichheit zwischen den Seiten noch eine Löschfreigabe.
- Alle zusätzlichen Rohspalten stehen im Bericht. Berichte aus eigenen Dateien
  können vertrauliche Daten enthalten und gehören nicht in öffentliche Issues.

ANLEITUNG.txt erläutert sämtliche Statusregeln, typische Fehler und Abhilfe.
Die Tests bilden ausgewählte lokale Fälle ab; feindliche parallele Eingriffe
ins Dateisystem und beliebige Folgeprozesse sind nicht vollständig untersucht.

Projekt und mögliche Übergabe
----------------------------
KIWERB bietet abgegrenzte Arbeitsergebnisse oder dokumentierte Lösungen zur
selbstständigen Nutzung. Vor einer individuellen Übergabe werden Datenschema,
Datenrechte, fachliche Abnahme, tatsächliche Umgebung und Bedienung geprüft.
Dieses Arbeitsbeispiel enthält keine Zusage von Hosting, Monitoring, laufender
Wartung, unbegrenztem Support oder einer bestimmten Geschäftsverbesserung.

Anbieter und Projektkontext: https://kiwerb.de/
