# pdf2md

Conversion locale de documents (PDF, Office, images) en Markdown, sous Windows, avant tout envoi à un LLM.

Un PDF transmis à un modèle passe en contexte sous forme d'images page par page, ce qui coûte 10 à 30 fois plus de tokens que le même contenu en markdown. pdf2md convertit en local et ne laisse sortir que du texte.

## Utilisation

| Geste | Résultat |
|:---|:---|
| Glisser 1 fichier sur `MARKDOWN.bat` | 1 fichier `.md` dans `out/` |
| Glisser plusieurs fichiers ou un dossier sur `MARKDOWN.bat` | 1 `.md` par fichier dans `out/`, arborescence conservée |
| Glisser les mêmes sur `MARKDOWN-FUSION.bat` | un seul `.md` daté regroupant tout |
| Double-clic sans rien glisser | traite le contenu de `entree/` |

Un dossier déposé est parcouru récursivement.

## Installation

1. Installer Python depuis python.org en cochant « Add python.exe to PATH ».
2. Cloner ou télécharger ce dépôt (bouton **Code > Download ZIP**), puis extraire, par exemple dans `C:\Outils\pdf2md\`.
3. Optionnel : créer un environnement isolé, détecté automatiquement par les `.bat` :
   ```
   python -m venv .venv
   ```
4. Premier lancement : les dépendances de `requirements.txt` s'installent seules (environ 1 minute).

## Formats

- Acceptés : `.pdf` `.docx` `.pptx` `.xlsx` `.csv` `.html` `.htm` `.txt` `.md` `.msg` `.epub` `.json` `.xml` `.zip` `.ipynb` `.rtf`, images `.png` `.jpg` `.jpeg` `.tif` `.tiff` `.bmp` `.webp`
- Refusés avec message explicite : `.doc` `.xls` `.ppt` (formats binaires Office 97-2003)

## Moteurs

- **PDF : PyMuPDF4LLM.** Restitue titres, ordre de lecture et tableaux en markdown pipe.
- **Autres formats : MarkItDown** (Microsoft).
- **OCR : Tesseract**, embarqué dans PyMuPDF.
- `--moteur markitdown` force MarkItDown partout.

## Nettoyage automatique

Actif par défaut. Retire en-têtes et pieds de page répétés, numéros de page isolés, filets décoratifs, césures de fin de ligne, espaces en rafale. Gain constaté : 20 à 30 % de tokens sur un rapport paginé.

Garde-fou : si la suppression des en-têtes retire plus de 35 % du texte, elle est annulée et la console affiche `ATTENTION`. Titres, tableaux, listes et citations ne sont jamais supprimés.

`--brut` désactive le nettoyage.

## Rapport console

```
OK   rapport_annuel.pdf    48 210 car.  ~13 391 tokens  (-27%)
```

Estimation à 3,6 caractères par token (français technique).

## OCR (PDF scannés)

Automatique : sous 80 caractères de texte natif par page, la page est traitée comme une image. Les fichiers concernés sont marqués `[OCR]`.

Le pack de langue (`fra` par défaut, 1,1 Mo) est téléchargé au premier besoin dans `tessdata/`, puis l'outil fonctionne hors ligne.

| Option | Effet |
|:---|:---|
| `--ocr auto` | défaut : OCR uniquement sans couche texte |
| `--ocr toujours` | force l'OCR |
| `--ocr jamais` | désactive l'OCR |
| `--langue eng` | autre langue (`deu`, `spa`, `ita`...) |

Une page océrisée perd sa structure (ni titres ni tableaux). Compter 1 à 2 s par page.

## Ligne de commande

```
python to_md.py "D:\Dossiers\Projet" --fusion Projet.md
python to_md.py fichier1.pdf fichier2.pdf --brut
python to_md.py entree --sortie "D:\Sortie"
python to_md.py --version
```

## Limites

- Tableaux sans bordures : ressortent à plat.
- Scans de mauvaise qualité : sortie vide signalée `VIDE ?`. Augmenter le DPI dans `ocr_document()` (300 par défaut).

## Confidentialité

`out/`, `entree/` et `tessdata/` sont exclus du dépôt par `.gitignore` : aucun document converti n'est versionné.

## Licence

AGPL-3.0, imposée par la dépendance PyMuPDF (AGPL-3.0). Voir `LICENSE`.
