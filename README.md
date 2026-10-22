# ComicTranslate IT · v0.1.0 (prototipo verificabile)

**Scopo:** sostituire testo inglese con lettering italiano in fumetti CBR/CBZ **senza riscrivere pixels fuori dall'area esplicitamente consentita**. È un prototipo funzionante e revisionabile, **non** un traduttore professionale interamente automatico.

## Avvio facile su Windows (consigliato)

**Non è necessario installare Python, usare PowerShell o installare 7-Zip.**

1. Apri [Windows portable in GitHub Actions](https://github.com/Rbocz/ComicTranslator/actions/workflows/windows-portable.yml).
2. Apri l'esecuzione più recente con spunta verde e scarica l'artifact **ComicTranslator-Windows-portatile**.
3. Estrai lo ZIP, poi fai doppio clic su **ComicTranslator.exe**.
4. Scegli un CBR/CBZ, la pagina, e premi **ANALIZZA I BALLOON**.
5. Al primo utilizzo dai il consenso al download del modello ONNX (verifica SHA-256).

Il programma mostra le proposte del detector. Le tavole originali non vengono alterate e **non sono inviate in rete**. Annotazioni e modello rimangono nella cartella locale utente. **Non è ancora un traduttore automatico completo.**

Alternativa usando il sorgente: fai doppio clic su **AVVIA_FACILE.bat**; se Python manca, ti chiederà prima il consenso per installarlo con winget.

Consulta anche [la guida breve](docs/WINDOWS_FACILE.md).

## Cosa fa già

- Importa CBZ e CBR (CBR richiede anche estrattore RAR, per es. 7-Zip/UnRAR), ordinando naturalmente le pagine; controlli dimensionali e lettura senza estrarre contenuto su disco.
- Crea un `project.json` non distruttivo (originale sempre conservato).
- OCR inglese con Tesseract; raggruppamento iniziale di righe; tentativo **prudente** di identificare balloon bianchi chiusi. I rettangoli senza balloon verificabile sono segnati come solo OCR.
- Possibilità di tradurre il testo di una pagina usando un endpoint chat OpenAI-compatible (API key separata, glossario e breve contesto delle pagine precedenti). **Non è inclusa traduzione automatica offline**.
- Editor Windows/Desktop con anteprima, modifica del testo, balloon rettangolari/ellittici e aggiunta manuale dei rettangoli delle lettere inglesi.
- Lettering con dimensione font adattiva e controllo dell'esatta posizione dei pixel rispetto alla forma/margine del balloon; se non ci sta, non si forza.
- Cancellazione conservativa delle lettere OCR in maschera, sfondo uniforme o inpainting locale OpenCV; conservazione dei pixel fuori area consentita.
- Export CBZ + `*.report.json`, **solo** delle regioni approvate. Gli errori lasciano intatto l'originale. Le pagine non modificate mantengono esattamente i bytes dell'immagine sorgente.

## Avvio semplificato su Windows

1. Installa **Python 3.12** (spuntare "Add Python to PATH") e **Tesseract OCR** con lingua inglese. Per input `.cbr` può servire anche un estrattore RAR (7-Zip o UnRAR) installato e nel PATH.
2. Estrai la cartella del progetto e fai doppio clic su **`AVVIA_WINDOWS.bat`**. Al primo utilizzo creerà un ambiente Python e installerà le dipendenze usando internet.
3. Si aprirà la scelta del file: seleziona fumetto `.cbz`/`.cbr` o progetto `.json`. Il programma crea il progetto accanto al fumetto e apre l'editor.
4. Premi **Rileva OCR** per ottenere suggerimenti, controlla le maschere, traduci e approva le zone che vuoi esportare.

*Non è ancora un programma `.exe` standalone: Python e Tesseract sono prerequisiti.*

## Installazione su Windows

Prerequisiti: Python 3.11 o 3.12 e [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) con inglese; 7-Zip/UnRAR per CBR. Python 3.13 non è ancora la nostra versione Windows di riferimento.

```powershell
cd comictranslate-it
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[cbr,cloud]"
comictranslate init "C:\fumetti\albo.cbz" --project "C:\fumetti\albo.project.json"
comictranslate scan "C:\fumetti\albo.project.json"
comictranslate gui "C:\fumetti\albo.project.json"
```

Se Tesseract non è nel PATH, impostare `TESSERACT_CMD` o modificare nel proprio Python la configurazione di `pytesseract.pytesseract.tesseract_cmd`; la scansione OCR funziona solo con Tesseract installato.

**Attenzione:** il progetto conserva il percorso relativo all'archivio sorgente; non spostare quest'ultimo senza aggiornare la voce `source` del JSON.

### Traduzione opzionale via API

Nessuna chiave API è inclusa. In PowerShell, nell'ambiente locale:

```powershell
$env:OPENAI_API_KEY = "LA_TUA_CHIAVE"
comictranslate translate "C:\fumetti\albo.project.json" --model gpt-4.1-mini
```

Il provider invia il **testo OCR**, non l'immagine intera. Verificare privacy, costi e attendibilità. **Le traduzioni restano non approvate.** La traduzione manuale tramite GUI funziona senza API.

### Esportazione

```powershell
comictranslate export "C:\fumetti\albo.project.json" --output "C:\fumetti\albo_italiano.cbz"
```

Il file `albo_italiano.report.json` elenca le regioni renderizzate, scartate e il metodo di pulizia. L'output è CBZ (non CBR) per mantenere un formato aperto di esportazione; i CBR sono leggibili come input.

## Flusso corretto di revisione

1. Scansiona o aggiungi balloon manualmente. Se il balloon è irregolare, l'OCR può suggerire una forma poligonale, ma l'editor v0.1 non consente ancora di editarne i vertici.
2. Controlla testo originale e **rettangoli gialli dei glifi da cancellare**. Per i balloon aggiunti manualmente usa `Segna testo da cancellare` nel balloon selezionato.
3. Inserisci e rivedi traduzione italiana; `Originale / anteprima` mostra la simulazione prima dell'approvazione.
4. Approva soltanto le regioni con OCR, forma e testo corretti. Controlla gli eventuali residui nell'anteprima: il detector attuale non è sufficiente per una garanzia editoriale.
5. Esporta, leggi il report e verifica visivamente tutte le pagine modificate.

## Sicurezza e limiti espliciti

- Nessun invio di immagini in rete; la traduzione cloud invia testo.
- Tutte le modifiche sono ristrette alla maschera ammessa; il resto dell'immagine non viene ritoccato.
- Su sfondi complessi, OpenCV Telea può lasciare artefatti: serve un futuro adapter LaMa e revisione manuale.
- Tesseract non è affidabile su tutte le font comic: implementeremo un modello specifico balloon+text come adapter separato. L'OCR potrebbe non rilevare tutte le parole; le maschere attuali possono lasciare aloni.
- Il sistema disegna attualmente lettering **nero** senza corsivo, grassetto misto o onomatopee dinamiche; non preserva ancora completamente lo stile della tavola.
- Il riconoscimento automatico non implica approvazione umana. Non promettiamo qualità editoriale senza controllo.
- L'output con lettering applicato è PNG a dimensioni originali: nessuna ricompressione JPEG delle pagine modificate.
- **Diritti:** usare soltanto fumetti che si è autorizzati a elaborare e distribuire. Le illustrazioni di prova sono sintetiche.

## Test

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python examples/create_demo.py
comictranslate init examples/demo_en.cbz --project examples/demo.project.json
comictranslate scan examples/demo.project.json
comictranslate gui examples/demo.project.json
```

Non è incluso il font del sistema operativo. Si usa un font locale TTF/OTF presente nella macchina; `comictranslate export ... --font C:\percorso\font.ttf` permette di specificarne uno.

## Architettura e roadmap

Vedi [`docs/DECISIONI.md`](docs/DECISIONI.md) per verifica delle repository, scelte di licenza e milestones. I componenti esterni sono documentati ma non incorporati senza analisi di manutenzione, licenza e prestazioni.


## Nuovo in v0.4: Annotatore ground truth e benchmark del detector

Per misurare quante nuvolette il riconoscitore **perde** (non soltanto quante ne trova),
è ora disponibile un editor locale di annotazioni e una valutazione con IoU,
precisione, recall, F1, categorie e regioni fuse.

```powershell
comictranslate annotate "capitolo.cbr" --page 5 --out "private_references/annotations.json"
comictranslate detector-eval "capitolo.cbr" "private_references/annotations.json" --out "private_references/quality.json"
```

**Importante:** soltanto le pagine segnate manualmente come *interamente controllate* entrano nel benchmark. Le immagini e il testo del fumetto **non** vengono incorporati nelle annotazioni.
Consulta [la guida all'annotazione](docs/ANNOTATION_WORKFLOW.md).


## v0.5 — RT-DETRv2 ONNX (detector neurale opzionale)

Il sistema può ora mostrare proposte del modello Apache-2.0 `ogkalu/comic-text-and-bubble-detector` e confrontarle con il rilevatore attuale sulle stesse pagine **verificate dall'annotatore**. I box sono approssimativi e non vengono trasformati in maschere di cancellazione; nessuna pagina è approvata automaticamente. I pesi ONNX non sono nel repository. Per installazione e comandi (`detector-fetch`, `detector-propose`, `detector-compare`), consulta la [guida](docs/LEARNED_DETECTOR.md).