# ComicTranslator 0.8 beta — Traduci fumetti CBR/CBZ

**Flusso completo disponibile:** scegli un fumetto → seleziona **Google Gemini** o **OpenAI** → inserisci la tua API key soltanto nell'app → traduci tutte le pagine → crea CBZ italiano → controlla le anteprime e correggi le traduzioni.

**Non è una traduzione editoriale perfetta.** Vision API e OCR possono mancare testo, le coordinate sono stime, e l'app **non altera sfondi complessi** quando il risultato sarebbe insicuro. L'output CBZ indica le pagine rimaste originali e i blocchi non applicati nel report. Non deve essere considerato una versione finale professionale senza revisione.

## Windows in tre passaggi

1. [Scarica l'ultima build verificata Windows](https://github.com/Rbocz/ComicTranslator/actions/workflows/windows-portable.yml) (artifact ZIP).
2. Estrai tutto, apri `ComicTranslator.exe` e premi **TRADUCI IL FUMETTO COMPLETO**.
3. Scegli il CBR, la cartella sul disco F:, provider e modello, incolla una chiave API, spunta il consenso all'invio delle pagine, avvia.

Non serve installare Python, Tesseract né il modello locale ONNX per il percorso di traduzione completa. I modelli ONNX sono opzionali e utilizzati solo dal vecchio strumento avanzato di annotazione.

## Informazioni essenziali

- **Google Gemini**: `gemini-2.5-flash`, API ufficiale GenerateContent.
- **OpenAI**: `gpt-4.1-mini`, API vision Chat Completions.
- Le immagini vengono inviate al provider soltanto dopo il consenso e **possono comportare costi**.
- Chiavi API conservate soltanto in memoria; non vengono salvate sul disco.
- Il CBR inglese originale non viene mai sovrascritto.
- Riprende le pagine elaborate se riparti sullo stesso file progetto.
- I report `.report.json` e `.errors.json` elencano le regioni incomplete o le pagine fallite.
- Modifica la traduzione italiana e usa **Riesporta CBZ** per aggiornare il risultato.

**[Guida completa con limiti e sicurezza](docs/FULL_WORKFLOW.md)**

Restano disponibili CLI, rilevatore RT-DETRv2, benchmark bilingue, annotatore ground truth e progetto JSON; sono strumenti avanzati non obbligatori per la traduzione.
