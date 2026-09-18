# Document Intelligence

Plateforme locale de traitement documentaire : transcription YouTube fidèle et conversion/fusion/découpage de PDF, sans dépendance cloud obligatoire.

Un seul outil, un seul système de jobs, une seule interface — accessible en ligne de commande ou via un dashboard web local.

## Fonctionnalités

**Transcription YouTube**
- Repli en cascade : sous-titres manuels → sous-titres automatiques → Whisper local, sans jamais inventer un mot.
- Chapitres, résumé, mots-clés et score de qualité générés localement (aucune clé API).
- Playlists, cache Whisper, multilingue automatique.

**Documents (PDF)**
- **PDF → Markdown** : titres, listes, tableaux, liens et images reconstruits fidèlement, gras/italique préservés, en-têtes/pieds de page répétés filtrés automatiquement.
- **Merge / Split** : fusion multi-fichiers avec sélection de pages, découpage par plages ou par lot.
- Suivi des traitements en arrière-plan (Jobs), bibliothèque de fichiers, historique.

## Démarrage rapide

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.webapp
```

Ouvrir **http://127.0.0.1:8000** — dashboard principal, transcription YouTube et outils PDF au même endroit.

> Local uniquement (`127.0.0.1`), sans authentification par défaut. Ne pas exposer sur un réseau public.

## Ligne de commande

```powershell
python -m src.cli "https://www.youtube.com/watch?v=VIDEO_ID"
```

Produit `transcript.md`, `transcript.txt` et les métadonnées dans `output/`. Voir `python -m src.cli --help` pour toutes les options (langue, modèle Whisper, mode recherche, etc.).

## Configuration

Valeurs par défaut modifiables via `config.yaml` (voir `config.example.yaml`) ou variables d'environnement (`YTT_*` pour la transcription, `DOCS_*` pour le module documentaire) — priorité : défauts → fichier → environnement → options CLI.

## Optionnel

| Besoin | Dépendance |
|---|---|
| Transcription audio (repli Whisper) | [ffmpeg](https://ffmpeg.org/) sur le PATH |
| OCR des PDF scannés | [Tesseract](https://github.com/tesseract-ocr/tesseract) sur le PATH |

Sans eux, l'outil fonctionne normalement pour le reste — message d'erreur clair si la fonctionnalité est réellement nécessaire, jamais de plantage.

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

~200 tests, aucun appel réseau réel (YouTube, Whisper et PDF simulés ou générés localement).

## Structure

```
src/
├── cli.py, webapp.py, pipeline.py     # Transcription YouTube
├── youtube/, transcription/, analysis/, exporters/
├── documents/                          # PDF → Markdown, Merge, Split (services, jobs, stockage)
├── static/documents/, templates/       # Interface web (dashboard, pages Documents)
tests/
```

## Sécurité et limites connues

- Contenu externe (PDF, sous-titres, titres) toujours traité comme non fiable : jamais exécuté, jamais interpolé dans une commande shell ; noms de fichiers et chemins protégés contre le path traversal.
- Aucun contournement de DRM ou de restriction d'accès — n'utiliser que sur du contenu légalement accessible.
- Pas de comptes ni de permissions multi-utilisateur (outil local mono-utilisateur assumé).
- Diarization (`--diarize`) et détection de tableaux PDF sont best-effort ; jamais de valeur inventée quand l'information est absente.
