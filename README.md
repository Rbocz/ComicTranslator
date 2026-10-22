# ComicTranslator — ComicTranslate IT v0.1.0

Prototipo di traduzione di comics inglesi verso italiano, orientato alla conservazione della tavola originale. **Non è ancora un sistema automatico di qualità editoriale.**

## Funzioni
- Importa CBZ/CBR (per CBR servono `rarfile` e UnRAR/7-Zip).
- Crea progetti JSON non distruttivi.
- OCR con Tesseract, rilevamento conservativo di balloon bianchi, modifiche manuali.
- Traduzione facoltativa con API OpenAI-compatible: invia il testo riconosciuto, non le immagini; richiede `OPENAI_API_KEY`.
- Lettering italiano adattato all'area consentita, pulizia localizzata, approvazione manuale prima dell'export CBZ.

## Windows
Installa Python 3.12 e Tesseract OCR (`eng`), poi avvia `AVVIA_WINDOWS.bat`. Il programma installa le librerie Python al primo avvio. Non è un EXE standalone.

## CLI
```sh
pip install -e '.[dev,cbr,cloud]'
comictranslate init input.cbz --project input.project.json
comictranslate scan input.project.json
comictranslate gui input.project.json
comictranslate export input.project.json --output output_it.cbz
pytest -q
```

## Limiti
Rilevamento e OCR non sono completi su balloon colorati e lettering elaborato. Pulizia OpenCV su sfondi complessi può lasciare artefatti. Il lettering è ancora monostile nero. Le traduzioni API richiedono revisione. Nessuna regione viene alterata se non è approvata e verificata dal motore. Usare solamente fumetti per i quali si possiedono i diritti necessari.

## Benchmark su edizioni tradotte (v0.2 sperimentale)

È disponibile un confronto **offline** di pagine inglesi e italiane, anche quando l'originale inglese contiene due pagine impilate. Il comando `reference-eval` calcola la trasformazione geometrica tramite SIFT/RANSAC e stima il riempimento tipografico delle righe italiane. `reference-profile` aggrega le misure; `apply-profile` memorizza nel progetto il riempimento medio desiderato, che il letterer usa come preferenza per suddividere le righe.

Vedi [la guida completa](docs/REFERENCE_BENCHMARK.md). Sono necessarie poche righe leggibili con Tesseract `ita`: non è addestramento di una rete neurale. **Le scansioni originali non sono incluse nel repository.**

## Abbinamento automatico CBR + riferimenti italiani (v0.3 sperimentale)

`comictranslate reference-match "albo.cbr" "pagina-it.png" --out private_references/matches.json`
identifica le pagine del capitolo inglese tramite caratteristiche grafiche SIFT+RANSAC.
`comictranslate reference-dataset "albo.cbr" "pagina1-it.png" "pagina2-it.png" --out private_references/report`
genera gli abbinamenti e i report offline, eliminando le duplicazioni delle pagine
anche se hai fornito crop parziali dello stesso fumetto. Aggiungi `--overlays`
soltanto quando desideri le anteprime private con le regioni rilevate.

Per il flusso completo, consulta [la guida](docs/CBR_REFERENCE_WORKFLOW.md).
I profili risultanti sono **provvisori**: non applicarli come verità editoriali
finché il riconoscimento dei balloon non avrà una copertura adeguata.
Su Windows è richiesto 7-Zip/UnRAR per CBR; su Linux/macOS è disponibile
l'accesso opzionale tramite `libarchive` di sistema.

## Roadmap
1. Benchmark controllato sui comics occidentali.
2. Detector specifico e OCR robusto.
3. Inpainting avanzato con maschere precise.
4. Lettering tipografico ed editor avanzato.
5. Eseguibile Windows e test visivi.

Questo progetto è autonomo, non incorpora codice di terzi senza verifica della licenza.


## v0.4 — Annotazioni verificate e benchmark del detector

Puoi ora disegnare poligoni e rettangoli per **ogni** balloon, didascalia, pensiero, onomatopea o testo incorporato nell'illustrazione. Il sistema distingue le proposte automatiche (non affidabili) dalle pagine **verificate completamente** dall'operatore e non conteggia mai le bozze come ground truth.

```powershell
comictranslate annotate "capitolo.cbr" --page 5 --out "private_references/annotations.json"
comictranslate detector-eval "capitolo.cbr" "private_references/annotations.json" --out "private_references/detection-report.json"
```

Misure: IoU, precisione, recall, F1, recall per categoria, falsi positivi, false negativi e regioni fuse. Vedi [guida al sistema di annotazione](docs/ANNOTATION_WORKFLOW.md). Le pagine del fumetto rimangono private.
