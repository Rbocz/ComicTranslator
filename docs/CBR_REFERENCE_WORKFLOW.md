# Capitolo EN + pagine italiane: preparazione dei riferimenti

## Come usare il CBR senza estrarre le immagini

Dopo aver installato il progetto e Tesseract OCR con la lingua italiana:

```powershell
comictranslate reference-match "chapter.cbr" "private_references\p1.png" "private_references\p2.png" --out "private_references\matches.json"
comictranslate reference-dataset "chapter.cbr" "private_references\p1.png" "private_references\p2.png" --out "private_references\reports" --overlays
```

Il motore abbina le pagine in base all'illustrazione con **SIFT + RANSAC**. Un
abbinamento viene proposto solo se ci sono almeno 35 punti geometrici validi
e un distacco di almeno 2,5x dal secondo candidato. Casi incerti restano da
verificare. Riferimenti parziali della stessa pagina non vengono conteggiati
due volte nel profilo di lettering.

I report prodotti sono `matches.json`, `page_NNN_metrics.json`, `summary.json`,
`lettering_profile.json` e, se richieste, anteprime `page_NNN_overlay.png`.
I primi quattro contengono esclusivamente metadata e misure, non i pixel
delle tavole. Le anteprime restano **private**.

Lettura CBR: Windows necessita rarfile e 7-Zip/UnRAR; sistemi con libarchive
installata possono usare la lettura nativa senza estrattori aggiuntivi.

## Risultati sul benchmark di sette pagine del capitolo (non replicati in CI)

- Archivio: 45 immagini.
- 9 riferimenti italiani assegnati automaticamente ad alta confidenza.
- 7 pagine inglesi distinte: indici 5–11 nell'archivio.
- 15 aree candidate a balloon, copertura chiaramente incompleta.
- Nessun balloon candidato sulle pagine 5 e 6.
- 7 candidati OCR utilizzabili per la mediana tipografica dopo aver
  escluso alcune regioni con linee aggregate (maggiore di 7).
- Preferenza sperimentale `target_line_fill=0.601`, che **non**
  rappresenta un valore validato di lettering professionale.

Questa calibrazione non deve essere applicata automaticamente ad altri titoli.
I limiti attuali sono il rilevamento dei balloon irregolari, il rischio di
regioni unite, la qualità dell'OCR e lo scarso numero di esempi utilizzabili.

## Piano di sviluppo dopo questo benchmark

1. Annotazioni manuali verificate delle regioni (balloon, didascalie, testo).
2. Detector specifico per comics occidentali, confrontato con misure
   di precisione/recall sul set annotato.
3. Segmentazione delle lettere inglesi e maschere di cancellazione verificate.
4. Inpainting di complessità progressiva, con divieto di modificare grafica
   fuori dalle maschere approvate.
5. OCR/editorial translation con glossario e revisione pagina per pagina.
6. Lettering condizionato da forma e font, benchmark visivo prima/dopo.

Non caricare fumetti/scansioni commerciali nella repository pubblica.
