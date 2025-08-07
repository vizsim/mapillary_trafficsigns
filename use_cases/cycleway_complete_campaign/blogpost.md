---
title: "Radwege ergänzen mit Mapillary-Verkehrszeichen (MapRoulette-Challenge)"
date: 2025-08-07
slug: "2025-maproulette-verkehrszeichen"
author: "Simon"
tags: ["osm", "mapillary", "maproulette", "radwege", "daten", "crowdsourcing"]
description: "Eine neue MapRoulette-Challenge hilft, fehlende Radwege in OSM zu finden – anhand automatisch erkannter Verkehrszeichen aus Mapillary."
---

## 🚴 Fehlende Radwege anhand von Verkehrszeichen ergänzen – neue MapRoulette-Challenge online

Für alle, die Radinfrastruktur in OpenStreetMap verbessern möchten, gibt es eine neue datenbasierte Herausforderung:

👉 **[MapRoulette-Challenge: Cycleway Completion Germany](https://maproulette.org/browse/challenges/52916)**

Diese Challenge basiert auf automatisch erkannten **radverkehrsbezogenen Verkehrszeichen** aus Mapillary-Bildern in Deutschland. Ziel ist es, **fehlende Radwege zu identifizieren und direkt in OSM zu ergänzen**.

---

## 🔍 Was steckt dahinter?

Ein Skript analysiert deutschlandweit Mapillary-Verkehrszeichenerkennungen (z. B. `DE:237`, `DE:240`, `DE:241`) und filtert nur jene heraus, die folgende Bedingungen erfüllen:

- 🚦 **Verkehrszeichen wurde erkannt** (Mapillary-API)
- 📆 **Mindestens 12 Monate regelmäßig sichtbar**
- 🆕 **Neueste Aufnahme stammt aus dem Jahr 2025**
- 🧭 **Kein OSM-Radweg innerhalb von 50 Metern** um das Schild

➡️ Diese Fälle sind besonders spannend, weil sie mit hoher Wahrscheinlichkeit auf **nicht gemappte Radinfrastruktur** hinweisen.

---

## 🗺️ So kannst du mitmachen

Jede Aufgabe in der MapRoulette-Challenge zeigt dir:

- 📷 Ein Mapillary-Bild an der Position
- 🗺️ Einen Link zum Ort in **[radinfra.de / TILDA](https://radinfra.de)**
- 🔗 Links zu hilfreichen Tools:
  - [Traffic Sign Tool](https://trafficsigns.osm-verkehrswende.org/)
  - [OSM-Wiki: Radverkehrsanlagen kartieren](https://wiki.openstreetmap.org/wiki/DE:Bicycle/Radverkehrsanlagen_kartieren)

Deine Aufgabe:

1. Prüfe die Stelle in Mapillary und radinfra.de / TILDA.
2. Ergänze ggf. fehlende OSM-Tags (z.B. `highway=cycleway`, `cycleway=*`, `bicycle=designated`, …).
3. Ist alles bereits korrekt gemappt, markiere die Aufgabe als **erledigt**.

---

## 🧪 Daten & Code

Der komplette Workflow – vom Datenabruf bis zur Aufgabenerstellung – ist offen dokumentiert:

🔗 [GitHub-Repository: mapillary_trafficsigns](https://github.com/vizsim/mapillary_trafficsigns)

Dort findest du:

- Python-Code zum Abrufen & Filtern der Daten
- GeoJSON-Erstellung für MapRoulette
- Hinweise zur Lizenzsituation der Mapillary-API
- Den konkreten Use-Case: **fehlende Radwege aufspüren**

---

## 💬 Fazit

Diese Challenge ist ein spannender Anwendungsfall für automatisierte Erkennung + Crowd-Mapping:  
**Machine Learning liefert den Hinweis – Menschen entscheiden, was wirklich fehlt.**

Mach mit und hilf dabei, das deutsche Radwegenetz in OSM vollständiger zu machen! 🚴‍♀️🗺️
