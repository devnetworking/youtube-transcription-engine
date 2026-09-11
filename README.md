# Transcription YouTube Intelligente

Outil de transcription YouTube qui privilégie toujours la source la plus fiable disponible : sous-titres manuels, puis sous-titres automatiques, puis reconnaissance vocale locale (Whisper) en dernier recours. Chaque vidéo produit un Markdown structuré et un texte brut, sans jamais inventer un mot qui n'a pas été prononcé.

Disponible en ligne de commande et via une petite interface web locale.

---

## Fonctionnalités

- **Stratégie de repli en cascade** : sous-titres manuels → sous-titres automatiques → audio + Whisper local, avec sélection automatique de la taille du modèle selon la mémoire disponible.
- **Fidélité garantie** : aucun mot inventé ; les passages incertains sont marqués explicitement (`[uncertain: ...]`) plutôt que remplacés par une supposition.
- **Nettoyage intelligent, non destructif** : suppression des doublons de sous-titres, chevauchements, ponctuation malformée — sans jamais réécrire le style de la personne qui parle.
- **Organisation automatique** : détection de chapitres (ceux de YouTube en priorité, sinon inférés par dérive thématique), résumé exécutif, sujets clés, termes techniques avec contexte, tout généré localement par heuristique (aucune clé API requise).
- **Multilingue** : langue détectée automatiquement ; l'analyse (mots-clés, résumé, chapitres, mode recherche) s'adapte à la langue au lieu d'utiliser des mots vides anglais sur du contenu français.
- **Playlists** : une URL de playlist est automatiquement développée en vidéos individuelles (plafonné à 50 par lot pour éviter un lancement massif accidentel).
- **Cache** : une transcription Whisper déjà faite (même vidéo, même langue, même modèle) est réutilisée au lieu de retélécharger l'audio et retranscrire.
- **Mode technique** : les commandes/lignes de code prononcées sont détectées et présentées dans un bloc de code, marquées comme reconstruites.
- **Mode recherche** (`--research-mode`) : extrait question de recherche, méthodologie, jeux de données, limites, etc., quand ils sont mentionnés.
- **Score de qualité** (HIGH / MEDIUM / LOW) basé uniquement sur des signaux observables (source, segments incertains).
- **Sécurité** : noms de fichiers assainis contre le path traversal, aucune commande shell construite à partir de texte non fiable, serveur web local sans exposition réseau par défaut.

## Sorties générées

```
output/<titre_video>/
├── transcript.md            # Markdown enrichi (résumé, chapitres, transcript, notes...)
├── transcript.txt           # Texte brut, sans mise en forme, pour NLP/RAG/archivage
├── metadata.json            # Métadonnées vidéo (null si non disponible, jamais inventé)
├── processing_report.json   # Statut, avertissements, score de qualité
├── chapters.json            # Chapitres détectés/inférés
└── raw_transcript.json      # Segments bruts horodatés
```

---

## Installation

Prérequis : Python 3.10+.

```powershell
cd "C:\Users\hamza\OneDrive\Documents\Transcript"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Optionnel — transcription audio locale (Whisper)** : nécessite [ffmpeg](https://ffmpeg.org/) sur le PATH.

```powershell
winget install --id Gyan.FFmpeg -e
# redémarrer le terminal ensuite
```

Sans ffmpeg, l'outil fonctionne normalement tant que des sous-titres YouTube existent ; seul le repli audio est indisponible (message d'erreur clair, pas de plantage).

---

## Utilisation — ligne de commande

```powershell
python -m src.cli "https://www.youtube.com/watch?v=VIDEO_ID"
```

Plusieurs vidéos en une seule commande :

```powershell
python -m src.cli URL1 URL2 URL3
```

Une URL de playlist fonctionne aussi — chaque vidéo est traitée individuellement :

```powershell
python -m src.cli "https://www.youtube.com/playlist?list=PLxxxxxxxx"
```

### Options principales

| Option | Description | Défaut |
|---|---|---|
| `--output` | Dossier de sortie | `output` |
| `--language` | Langue préférée, ou `auto` | `auto` |
| `--model` | Taille du modèle Whisper (`tiny`/`base`/`small`/`medium`/`large-v3`/`auto`) | `auto` |
| `--force-whisper` | Ignore les sous-titres, transcrit toujours l'audio | désactivé |
| `--no-prefer-captions` | Désactive la préférence pour les sous-titres | activé |
| `--no-timestamps` | Retire les horodatages du transcript | horodatages activés |
| `--no-chapters` | Désactive la détection/inférence de chapitres | activée |
| `--no-summary` | Désactive le résumé et les points clés | activé |
| `--research-mode` | Ajoute une section d'analyse recherche | désactivé |
| `--remove-filler-words` | Retire les mots de remplissage (um, euh...) | désactivé |
| `--diarize` | Tentative de distinction des locuteurs (voir Limitations) | désactivé |
| `--config` | Fichier de configuration YAML | — |
| `--verbose` | Affiche les diagnostics internes de yt-dlp | désactivé |

`python -m src.cli --help` affiche la liste complète.

---

## Utilisation — interface web locale

```powershell
python -m src.webapp
```

Puis ouvrir **http://127.0.0.1:8000**. Si ce port est déjà utilisé par un autre service sur la machine :

```powershell
python -m src.webapp --port 8791
```

Coller une URL, ajuster les options avancées si besoin, cliquer sur *Transcrire*. La progression s'affiche en direct, et les fichiers générés sont accessibles en un clic une fois la tâche terminée.

> **Important** : ce serveur n'a ni authentification ni protection contre les abus. Il écoute uniquement sur `127.0.0.1` par défaut — ne pas l'exposer sur un réseau ou Internet sans ajouter une authentification, sous peine d'en faire un relais ouvert pour télécharger n'importe quelle vidéo YouTube depuis la machine.
>
> Le serveur ne recharge pas le code automatiquement : après une mise à jour du projet, il faut l'arrêter (`Ctrl+C`) et le relancer.

---

## Configuration

Un fichier YAML peut fixer les valeurs par défaut (voir `config.example.yaml`) :

```yaml
output_dir: output
language: auto
prefer_captions: true
whisper_model: auto
timestamps: true
chapter_detection: true
generate_summary: true
```

```powershell
python -m src.cli "URL" --config config.yaml
```

Les variables d'environnement `YTT_<NOM_CHAMP>` (ex. `YTT_WHISPER_MODEL=small`) surchargent le fichier de config, lui-même surchargé par les options de ligne de commande.

---

## Stratégie de transcription

1. **Sous-titres manuels YouTube** — utilisés si disponibles, quelle que soit la langue.
2. **Sous-titres automatiques YouTube** — repli si aucun sous-titre manuel n'existe.
3. **Audio + Whisper local** — dernier recours : extraction audio via yt-dlp/ffmpeg, transcription via `faster-whisper`, taille de modèle choisie automatiquement selon la mémoire disponible (sauf `--model` explicite).

Chaque changement de palier est signalé dans les logs et dans `processing_report.json`.

---

## Structure du projet

```
src/
├── cli.py                 # Point d'entrée ligne de commande (Typer)
├── webapp.py               # Point d'entrée serveur web (Flask)
├── pipeline.py              # Logique de traitement partagée CLI + web
├── config.py, models.py, exceptions.py
├── youtube/                # metadata.py, captions.py, audio.py
├── transcription/          # engine.py (repli), whisper_engine.py, cleanup.py
├── analysis/                # chapters.py, summary.py, keywords.py, quality.py, enrich.py, technical.py
├── exporters/                # markdown_exporter.py, text_exporter.py, json_exporter.py, blocks.py
├── utils/                    # filenames.py, timestamps.py, cache.py, validation.py
└── templates/index.html      # Page de l'interface web
tests/                        # ~83 tests, tout est mocké (aucun appel réseau réel)
```

---

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

Tous les appels à YouTube, yt-dlp et Whisper sont simulés (`monkeypatch`) — aucun test ne télécharge de vraie vidéo.

---

## Limitations connues

- **Diarization** (distinction des locuteurs) : `--diarize` est accepté mais n'effectue pas de vraie diarization — les étiquettes de locuteur sont volontairement omises plutôt qu'inventées. Une intégration réelle (`pyannote.audio`) nécessiterait un jeton Hugging Face et des modèles supplémentaires.
- **Cache** : ne couvre que le palier Whisper (téléchargement audio + transcription) — les sous-titres YouTube sont toujours récupérés à nouveau à chaque exécution, car cette requête est déjà rapide et peu coûteuse.
- **Whisper** : la précision dépend de la taille du modèle choisie ; le modèle `base`/`tiny` peut produire des erreurs de transcription sur de l'audio bruité.
- **Changement de langue en cours de vidéo** : la langue détectée est unique par vidéo ; les transitions linguistiques internes (`[Language: French]` / `[Language: English]`) ne sont pas étiquetées.

---

## Sécurité et usage responsable

- N'utilisez cet outil que sur des vidéos auxquelles vous avez légalement accès. Aucun contournement de DRM, d'authentification ou de restriction d'âge n'est implémenté.
- Le texte extrait (titres, sous-titres, transcript) est toujours traité comme non fiable : jamais exécuté, jamais interpolé directement dans une commande shell.
