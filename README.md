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

## Roadmap
1. Benchmark controllato sui comics occidentali.
2. Detector specifico e OCR robusto.
3. Inpainting avanzato con maschere precise.
4. Lettering tipografico ed editor avanzato.
5. Eseguibile Windows e test visivi.

Questo progetto è autonomo, non incorpora codice di terzi senza verifica della licenza.
