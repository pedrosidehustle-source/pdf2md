#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF -> MARKDOWN.  Objectif : ne plus jamais donner un PDF brut a un LLM.

Usage :
    glisser-deposer des fichiers OU des dossiers sur MARKDOWN.bat
    ou double-clic sur MARKDOWN.bat  -> traite le dossier  entree/

Options :
    --fusion Dossier.md   tout regrouper dans un seul .md (ideal pour 15 PDF d'un coup)
    --brut                sans nettoyage (garde les en-tetes/pieds de page repetes)
    --moteur markitdown   forcer MarkItDown meme sur les PDF
    --sortie D:\\chemin     dossier de sortie (defaut : out/)
"""

import argparse
import os
import re
import sys
import tempfile
import time
from pathlib import Path

VERSION = "2.1"
DATE_VERSION = "27/08/2026"

RACINE = Path(__file__).resolve().parent
ENTREE = RACINE / "entree"
SORTIE = RACINE / "out"

EXT_IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
EXT_SUPPORTEES = ({".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html", ".htm",
                   ".txt", ".md", ".msg", ".epub", ".json", ".xml", ".zip",
                   ".ipynb", ".rtf"} | EXT_IMAGES)
# formats binaires Office 97-2003 : aucun convertisseur fiable, on previent au lieu d'echouer
EXT_REFUSEES = {".doc": "Word 97-2003", ".xls": "Excel 97-2003", ".ppt": "PowerPoint 97-2003"}

# ratio moyen caracteres/token constate sur du francais technique
CAR_PAR_TOKEN = 3.6

try:
    from markitdown import MarkItDown
    MID = MarkItDown(enable_plugins=False)
except ImportError:
    sys.exit("[STOP] Lancer :  pip install \"markitdown[pdf,docx,pptx,xlsx]\" pymupdf4llm")

try:
    import pymupdf4llm
    import pymupdf
    PYMUPDF = True
except ImportError:
    PYMUPDF = False


# --------------------------------------------------------------------------
# OCR — pour les PDF scannes (image sans couche texte)
# --------------------------------------------------------------------------
TESSDATA = RACINE / "tessdata"
URL_TESS = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{}.traineddata"


def preparer_ocr(langue: str):
    """Installe au besoin les packs de langue et pointe MuPDF dessus. -> (ok, message)"""
    TESSDATA.mkdir(exist_ok=True)
    # 'eng' est indispensable : MuPDF declenche son propre OCR en anglais sur toute
    # page restee sans texte, et plante si le pack est absent.
    besoins = [langue] if langue == "eng" else [langue, "eng"]
    for lang in besoins:
        fichier = TESSDATA / f"{lang}.traineddata"
        if fichier.exists() and fichier.stat().st_size > 100_000:
            continue
        fichier.unlink(missing_ok=True)
        print(f"  Telechargement du pack OCR '{lang}' (une seule fois)...")
        try:
            import urllib.request
            urllib.request.urlretrieve(URL_TESS.format(lang), fichier)
            if fichier.stat().st_size < 100_000:
                raise ValueError("fichier incomplet")
        except Exception as e:
            fichier.unlink(missing_ok=True)
            return False, (f"pack OCR '{lang}' non telecharge ({str(e)[:60]}). "
                           f"Le deposer manuellement dans {TESSDATA}")
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA)
    return True, None


def caracteres_natifs(chemin: Path):
    """Caracteres de texte natif, page par page."""
    try:
        doc = pymupdf.open(str(chemin))
    except Exception:
        return None
    mesures = [len(p.get_text().strip()) for p in doc]
    doc.close()
    return mesures


def ocr_document(chemin: Path, langue: str, a_ocriser: set, dpi: int = 300) -> Path:
    """N'OCRise que les pages listees ; les pages natives sont conservees telles
    quelles, ce qui preserve leur structure (titres, tableaux)."""
    src = pymupdf.open(str(chemin))
    sortie = pymupdf.open()
    for i, page in enumerate(src):
        if i in a_ocriser:
            print(f"      OCR page {i + 1}/{src.page_count}...", end="\r", flush=True)
            pix = page.get_pixmap(dpi=dpi)
            sortie.insert_pdf(pymupdf.open("pdf", pix.pdfocr_tobytes(language=langue, tessdata=str(TESSDATA))))
        else:
            sortie.insert_pdf(src, from_page=i, to_page=i)
    cible = Path(tempfile.gettempdir()) / f"_ocr_{os.getpid()}_{chemin.stem[:40]}.pdf"
    sortie.save(str(cible))
    src.close()
    sortie.close()
    print(" " * 44, end="\r")
    return cible


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------
def convertir(chemin: Path, moteur: str, mode_ocr: str = "auto", langue: str = "fra"):
    """Retourne (texte_complet, liste_des_pages, nb_pages_ocrisees)."""
    nb_ocr = 0
    temporaire = None

    if chemin.suffix.lower() in EXT_IMAGES:
        if not (PYMUPDF and mode_ocr != "jamais"):
            return "", [""], 0
        ok, message = preparer_ocr(langue)
        if not ok:
            print(f"      [!] {message}")
            return "", [""], 0
        img = pymupdf.open(str(chemin))
        pix = img[0].get_pixmap(dpi=300)
        doc = pymupdf.open("pdf", pix.pdfocr_tobytes(language=langue, tessdata=str(TESSDATA)))
        texte = doc[0].get_text()
        img.close()
        doc.close()
        return texte, [texte], 1

    if chemin.suffix.lower() == ".pdf" and PYMUPDF and mode_ocr != "jamais":
        mesures = caracteres_natifs(chemin)
        if mesures:
            # page par page : un document mixte (texte + un scan insere) doit voir
            # sa seule page scannee passer a l'OCR, sans degrader les autres.
            if mode_ocr == "toujours":
                a_ocriser = set(range(len(mesures)))
            else:
                a_ocriser = {i for i, n in enumerate(mesures) if n < 80}
            if a_ocriser:
                ok, message = preparer_ocr(langue)
                if not ok:
                    print(f"      [!] {message}")
                else:
                    temporaire = ocr_document(chemin, langue, a_ocriser)
                    nb_ocr = len(a_ocriser)

    source = temporaire or chemin
    try:
        if source.suffix.lower() == ".pdf" and PYMUPDF and moteur != "markitdown":
            try:
                blocs = pymupdf4llm.to_markdown(str(source), page_chunks=True,
                                                show_progress=False)
                pages = [b.get("text", "") for b in blocs]
                return "\n\n".join(pages), pages, nb_ocr
            except Exception as e:
                # dernier filet : l'OCR interne de MuPDF (anglais, non configurable)
                # peut echouer si les packs sont absents. On sauve le fichier.
                if "esseract" not in str(e) and "language initialisation" not in str(e):
                    raise
                print("      [!] OCR interne de PyMuPDF indisponible -> repli MarkItDown")
        texte = MID.convert(str(source)).text_content
        return texte, decouper_pages(texte), nb_ocr
    finally:
        if temporaire:
            temporaire.unlink(missing_ok=True)


def decouper_pages(texte: str):
    """Restitue la liste des pages, quel que soit le separateur du moteur."""
    if "\f" in texte:
        return texte.split("\f")
    if "\n-----\n" in texte:
        return texte.split("\n-----\n")
    return [texte]


# --------------------------------------------------------------------------
# Nettoyage : c'est la que se gagnent les tokens
# --------------------------------------------------------------------------
def est_contenu(ligne: str) -> bool:
    """Vrai si la ligne porte du contenu : jamais candidate a la suppression."""
    nue = ligne.strip()
    if nue.startswith(("#", "|", ">", "-", "*", "+", "```")):
        return True                      # titre, tableau, citation, liste, code
    if len(nue.split()) > 12:
        return True                      # un en-tete/pied fait rarement 12 mots
    if len(nue) > 120:
        return True
    return False


def signature(ligne: str) -> str:
    """Neutralise le seul numero de page pour reconnaitre un motif recurrent."""
    return re.sub(r"\b\d{1,4}\b", "#", ligne.strip())


def lignes_recurrentes(pages):
    """En-tetes / pieds de page repetes : 1re et derniere ligne utile de chaque page."""
    if len(pages) < 4:
        return set()
    compteur = {}
    numero_seul = re.compile(r"(page\s*)?\d{1,4}(\s*/\s*\d{1,4})?", re.I)
    for page in pages:
        lignes = [l for l in page.splitlines()
                  if l.strip() and not numero_seul.fullmatch(l.strip())]
        if not lignes:
            continue
        for ligne in {lignes[0], lignes[-1]}:
            if 3 <= len(ligne.strip()) <= 120 and not est_contenu(ligne):
                sig = signature(ligne)
                compteur[sig] = compteur.get(sig, 0) + 1
    seuil = max(4, int(len(pages) * 0.6))
    return {s for s, n in compteur.items() if n >= seuil}


def _appliquer(pages, motifs):
    propres = []
    for page in pages:
        gardees = []
        for ligne in page.splitlines():
            nue = ligne.strip()
            if not nue:
                gardees.append("")
                continue
            if motifs and signature(ligne) in motifs and not est_contenu(ligne):
                continue                                   # en-tete / pied repete
            if re.fullmatch(r"[-–—_=•·.\s]{3,}", nue):
                continue                                   # filet decoratif
            if re.fullmatch(r"(page\s*)?\d{1,4}(\s*/\s*\d{1,4})?", nue, re.I):
                continue                                   # numero de page isole
            gardees.append(ligne.rstrip())
        propres.append("\n".join(gardees))

    texte = "\n\n".join(propres)
    texte = re.sub(r"(\w)-\n(\w)", r"\1\2", texte)          # cesures de fin de ligne
    texte = re.sub(r"[ \t]{2,}", " ", texte)                # espaces multiples
    texte = re.sub(r" +\n", "\n", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)                # lignes vides en rafale
    texte = re.sub(r"\*\*\s*\*\*", "", texte)               # gras vides (pymupdf)
    return texte.strip() + "\n"


def nettoyer(texte: str, pages=None):
    """Retourne (texte_nettoye, alerte_ou_None)."""
    pages = pages if pages else decouper_pages(texte)
    motifs = lignes_recurrentes(pages)
    resultat = _appliquer(pages, motifs)

    # garde-fou : une suppression massive signale une heuristique qui s'emballe
    if motifs and len(texte) and len(resultat) / len(texte) < 0.65:
        prudent = _appliquer(pages, set())
        if len(prudent) > len(resultat):
            return prudent, ("suppression des en-tetes annulee (trop de contenu retire) "
                             "- relancer avec --brut en cas de doute")
    return resultat, None


def jetons(texte: str) -> int:
    return int(len(texte) / CAR_PAR_TOKEN)


# --------------------------------------------------------------------------
# Collecte des fichiers
# --------------------------------------------------------------------------
def collecter(cibles, racine_entree=None):
    """Retourne [(fichier, racine)] : la racine sert a reconstruire l'arborescence.

    - dossier depose        -> racine = son parent, le dossier lui-meme est donc recree
    - dossier entree/       -> racine = entree/, on ne recree pas 'entree' dans out/
    - fichier isole depose  -> racine = son parent, il atterrit a la racine de out/
    """
    trouves, ignores = [], []
    for cible in cibles:
        p = Path(cible)
        if p.is_dir():
            racine = p if (racine_entree and p.resolve() == racine_entree.resolve()) else p.parent
            for f in sorted(p.rglob("*")):
                if not f.is_file() or f.name.startswith("~$") or f.name == "_LISEZ-MOI.txt":
                    continue
                ext = f.suffix.lower()
                if ext in EXT_SUPPORTEES:
                    trouves.append((f, racine))
                elif ext in EXT_REFUSEES:
                    print(f"  IGNORE  {f.name} : format {EXT_REFUSEES[ext]} non pris en "
                          f"charge, le reenregistrer au format moderne")
                elif ext:
                    ignores.append(f.name)
        elif p.is_file() and p.suffix.lower() in EXT_SUPPORTEES:
            trouves.append((p, p.parent))
        elif p.exists():
            libelle = EXT_REFUSEES.get(p.suffix.lower())
            if libelle:
                print(f"  IGNORE  {p.name} : format {libelle} non pris en charge, "
                      f"le reenregistrer au format moderne")
            else:
                print(f"  IGNORE  {p.name} (extension non prise en charge)")
        else:
            print(f"  ABSENT  {cible}")
    if ignores:
        apercu = ", ".join(sorted(set(Path(n).suffix.lower() for n in ignores)))
        print(f"  IGNORE  {len(ignores)} fichier(s) d'extension non prise en charge ({apercu})")
    vus, uniques = set(), []
    for f, racine in trouves:
        cle = f.resolve()
        if cle not in vus:
            vus.add(cle)
            uniques.append((f, racine))
    return uniques


def chemin_sortie(src: Path, racine: Path, sortie: Path, plat: bool) -> Path:
    """Reconstruit l'arborescence source sous out/, sauf en mode plat."""
    if plat:
        return nom_unique(sortie, src.stem, src.suffix)
    try:
        relatif = src.resolve().relative_to(racine.resolve())
    except ValueError:
        relatif = Path(src.name)
    dossier = sortie / relatif.parent
    dossier.mkdir(parents=True, exist_ok=True)
    return nom_unique(dossier, src.stem, src.suffix)


def nom_unique(dossier: Path, base: str, ext_source: str = "") -> Path:
    base = re.sub(r'[<>:"/\\|?*]', "-", base)[:80]
    cible = dossier / f"{base}.md"
    if cible.exists() and ext_source:
        cible = dossier / f"{base}.{ext_source.lstrip('.')}.md"
    n = 2
    while cible.exists():
        cible = dossier / f"{base}_{n}.md"
        n += 1
    return cible


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=f"PDF / Office -> markdown (v{VERSION})")
    ap.add_argument("--version", action="version",
                    version=f"pdf2md v{VERSION} du {DATE_VERSION}")
    ap.add_argument("cibles", nargs="*", help="fichiers ou dossiers")
    ap.add_argument("--fusion", default=None, metavar="NOM.md")
    ap.add_argument("--brut", action="store_true")
    ap.add_argument("--plat", action="store_true",
                    help="tout mettre a la racine de out/ sans recreer l'arborescence")
    ap.add_argument("--moteur", choices=["auto", "markitdown"], default="auto")
    ap.add_argument("--ocr", choices=["auto", "toujours", "jamais"], default="auto",
                    help="auto = seulement si le PDF n'a pas de couche texte")
    ap.add_argument("--langue", default="fra", help="langue OCR : fra, eng, deu...")
    ap.add_argument("--sortie", default=None)
    args = ap.parse_args()

    sortie = Path(args.sortie) if args.sortie else SORTIE
    sortie.mkdir(parents=True, exist_ok=True)

    cibles = args.cibles or [ENTREE]
    if not args.cibles:
        ENTREE.mkdir(exist_ok=True)
    fichiers = collecter(cibles, ENTREE)
    if not fichiers:
        sys.exit(f"[STOP] Rien a convertir. Deposer des fichiers dans {ENTREE} "
                 f"ou les glisser sur MARKDOWN.bat")

    if args.ocr != "jamais" and PYMUPDF:
        ok, message = preparer_ocr(args.langue)
        if not ok:
            print(f"  [!] {message}\n      -> poursuite sans OCR")
            args.ocr = "jamais"

    moteur_pdf = "PyMuPDF4LLM" if (PYMUPDF and args.moteur == "auto") else "MarkItDown"
    print(f"pdf2md v{VERSION} ({DATE_VERSION})")
    print(f"Moteur PDF : {moteur_pdf}   |   {len(fichiers)} fichier(s)   |   "
          f"nettoyage : {'non' if args.brut else 'oui'}   |   "
          f"OCR : {args.ocr}" + (f" ({args.langue})" if args.ocr != "jamais" else "") + "\n")

    depart = time.time()
    total_avant = total_apres = 0
    morceaux, produits, echecs = [], [], 0

    for src, racine in fichiers:
        t0 = time.time()
        try:
            texte, pages, nb_ocr = convertir(src, args.moteur, args.ocr, args.langue)
        except Exception as e:
            detail = str(e)[:90]
            if "esseract" in detail or "language initialisation" in detail:
                detail = ("packs OCR incomplets. Supprimer le dossier tessdata\\ puis "
                          "relancer (ils seront retelecharges), ou utiliser --ocr jamais")
            print(f"  ECHEC   {src.name} -> {detail}")
            echecs += 1
            continue

        avant = len(texte)
        alerte = None
        if not args.brut:
            texte, alerte = nettoyer(texte, pages)
        apres = len(texte)
        total_avant += avant
        total_apres += apres
        if alerte:
            print(f"  ATTENTION  {src.name} : {alerte}")

        if src.suffix.lower() == ".pdf" and apres / max(1, len(pages)) < 80:
            print(f"  VIDE ?  {src.name} -> {apres} car. pour {len(pages)} page(s) : "
                  f"ni texte ni OCR exploitable (page blanche ou scan illisible)")

        try:
            etiquette = str(src.resolve().relative_to(racine.resolve()))
        except ValueError:
            etiquette = src.name

        if args.fusion:
            morceaux.append(f"\n\n# FICHIER : {etiquette}\n\n{texte}")
        else:
            cible = chemin_sortie(src, racine, sortie, args.plat)
            cible.write_text(texte, encoding="utf-8")
            produits.append(cible)

        gain = 100 * (1 - apres / avant) if avant else 0
        gain_txt = f"-{gain:.0f}%" if gain >= 0 else f"+{-gain:.0f}%"
        marque = f" [OCR {nb_ocr}p]" if nb_ocr else ""
        court = etiquette if len(etiquette) <= 40 else "..." + etiquette[-37:]
        print(f"  OK{marque:10} {court:40} {apres:>8} car. "
              f"~{jetons(texte):>7} tokens  ({gain_txt:>5})  ({time.time() - t0:.1f}s)")

    if args.fusion and morceaux:
        cible = sortie / args.fusion
        entete = (f"<!-- {len(morceaux)} document(s) converti(s) le "
                  f"{time.strftime('%d/%m/%Y')} -->\n")
        cible.write_text(entete + "".join(morceaux), encoding="utf-8")
        produits.append(cible)

    arbo = "a plat" if args.plat else "arborescence source reproduite"
    print(f"\n{len(produits)} fichier(s) dans {sortie}  ({arbo})")
    if total_avant:
        print(f"Volume : {total_apres:,} car.  ~{jetons('x' * total_apres):,} tokens "
              f"estimes  (nettoyage : -{100 * (1 - total_apres / total_avant):.0f}%)"
              .replace(",", " "))
    if echecs:
        print(f"{echecs} echec(s)")
    print(f"{time.time() - depart:.1f}s")


if __name__ == "__main__":
    main()
