# Benchmark di lettering professionale (offline)

## Scopo
Le immagini della stessa tavola in inglese e italiano permettono di **misurare** allineamento, balloon chiari e disposizione tipografica. Non bastano per addestrare un detector universale e non forniscono una maschera perfetta dei caratteri. Il modulo non effettua richieste web né carica le scansioni.

## Esempio di utilizzo

```powershell
comictranslate reference-eval private_references/ref1-2eng.png private_references/ref1.png --part 1 --out reference_reports/p1.json --overlay reference_reports/p1_overlay.png
comictranslate reference-eval private_references/ref1-2eng.png private_references/ref2.png --part 2 --out reference_reports/p2.json --overlay reference_reports/p2_overlay.png
comictranslate reference-eval private_references/ref3eng.png private_references/ref3.png --out reference_reports/p3.json --overlay reference_reports/p3_overlay.png
comictranslate reference-profile reference_reports/p1.json reference_reports/p2.json reference_reports/p3.json --out reference_reports/lettering_profile.json
comictranslate apply-profile mio_albo.project.json reference_reports/lettering_profile.json
comictranslate export mio_albo.project.json --output mio_albo_it.cbz
```

Per misurare righe italiane, installa anche Tesseract OCR con i dati della lingua **ita**. Senza italiano, l'allineamento continua ma le misure delle righe non sono disponibili.

## Interpretazione
- `alignment.inliers`: numero di corrispondenze grafiche valide (non è il numero di balloon).
- `alignment.rms_px`: errore residuo geometrico in pixel della scansione italiana.
- `candidate_balloon_count`: proposte conservative di balloon chiari, non la conta reale di tutte le nuvolette.
- `mean_line_fill`: occupazione stimata della larghezza interna su righe OCR leggibili.
- `target_line_fill`: mediana limitata fra 0.50 e 0.86. Può essere applicata come **preferenza** nel motore di spezzatura delle righe; non autorizza automaticamente la pulizia.

**Limitazioni note:** i balloon aperti, scuri, sovrapposti e le didascalie non vengono ancora rilevati in modo esaustivo; anche ridimensionamenti e differenze cromatiche cambiano i pixel. Usare solo scansioni e opere per le quali si possiedono i diritti necessari. La repository pubblica NON deve contenere le pagine del fumetto.
