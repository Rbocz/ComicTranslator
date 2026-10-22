# Detector neurale ONNX — pilot verificabile (v0.5)

Il detector precedente trovava solo regioni luminose chiuse. Il nuovo adapter
aggiunge un **rilevatore RT-DETRv2** che riconosce 3 classi (`bubble`,
`text_bubble`, `text_free`) e collega i box di testo alla nuvoletta più piccola
che li contiene. È un **pilota**: il modello produce rettangoli, non maschere
pixel-perfect; le proposte non vanno mai usate come autorizzazione a cancellare.

Modello: [`ogkalu/comic-text-and-bubble-detector`](https://huggingface.co/ogkalu/comic-text-and-bubble-detector),
Apache-2.0; file `detector-v4-s_int8.onnx` a revisione
`43838e758e4a097f7dc42f001ac8c8b79ed6ebe5`. Lo scaricamento è esplicito;
verifichiamo sempre la firma SHA-256 pubblicata dal model host. I pesi rimangono
sul PC dell'utente e **non** sono nella repository.

## Installazione (Windows con Python 3.12)

```powershell
python -m pip install -e ".[cbr,detector,dev]"
comictranslate detector-fetch --out models/detector-v4-s_int8.onnx
```

Il download necessita Internet una sola volta. ONNX Runtime CPU è il primo
provider supportato; misureremo l'accelerazione GPU solo dopo averne verificato
compatibilità, driver e risultato numerico. Per leggere CBR su Windows occorre
7-Zip/UnRAR secondo la guida principale.

## Esecuzione di prova sul CBR, SENZA modifiche alle immagini

```powershell
comictranslate detector-propose "capitolo.cbr" --pages 5,6,7,8,9,10,11 --model-file models/detector-v4-s_int8.onnx --out private_references/onnx-proposals.json
```

Per vedere le regioni sull'immagine (rettangoli tratteggiati, NON verificati):

```powershell
comictranslate annotate "capitolo.cbr" --page 5 --detector onnx --model-file models/detector-v4-s_int8.onnx --out private_references/annotations.json
```

Un campo `role=balloon_box_approx` è un rettangolo associato al balloon;
`unattached_text_box` indica testo senza balloon trovato;
`free_text_box` indica testo esterno. Tutti restano `needs_review: true`.

## Benchmark corretto: confronto con ground truth umano

Soltanto **dopo** aver disegnato manualmente le regioni e marcato le pagine
*completamente verificate* nell'editor:

```powershell
comictranslate detector-compare "capitolo.cbr" private_references/annotations.json --model-file models/detector-v4-s_int8.onnx --out private_references/comparison.json
```

Il report include TP, FP, FN, recall, precision, F1 e metriche per pagina,
con confronto sullo **stesso** set verificato. Se non ci sono pagine verificate,
il programma si ferma e non inventa punteggi.

## Limiti e qualità

- L'accuratezza reale su *Absolute Batman* **non è stata ancora misurata** con
  questo modello: i pesi ONNX non erano scaricabili nell'ambiente di sviluppo.
- Il modello è stato addestrato su fumetti di più tipologie; è necessario
  verificare il comportamento su caption, forme irregolari, lettere dipinte e SFX.
- Nessuna nuova funzione ha accesso alle maschere definitive di pulizia:
  occorrerà una fase distinta di segmentazione precisa e supervisione umana.
- Le tavole commerciali e le annotazioni locali rimangono escluse dal repository.

Per controllare una distribuzione del modello includere anche gli avvisi di
attribuzione richiesti dalla licenza Apache-2.0.