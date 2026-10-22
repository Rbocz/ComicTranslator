# v0.4 — Annotazioni verificabili per fumetti occidentali

Il sistema finora rileva bene **alcuni** balloon bianchi e chiusi, ma ne perde molti sulle pagine complesse. La nuova fase separa rigorosamente **proposta automatica** e **ground truth umana**.

## Annotazione delle pagine inglesi direttamente dal CBR

Con Python e le dipendenze installate, da PowerShell:

```powershell
comictranslate annotate "C:\fumetti\capitolo.cbr" --page 5 --out "private_references\batman-annotations.json"
```

Nell'editor puoi:
- passare da una pagina all'altra o aprire direttamente la pagina 5;
- scegliere una categoria: **dialogue**, **caption**, **thought**, **sfx**, **art_text**;
- disegnare una forma **poligonale** con clic sui vertici e Invio per concludere;
- usare una **forma rettangolare** trascinando il mouse;
- correggere o cancellare una regione; vedere, senza approvarli, i poligoni suggeriti dal rilevatore;
- contrassegnare **"Pagina interamente controllata"** soltanto dopo avere verificato tutti i balloon e i testi della pagina (compresi quelli scuri e le scritte integrate nell'illustrazione).

Quando aggiungi/modifichi una regione, l'approvazione della pagina decade automaticamente. Lo strumento salva soltanto **coordinate normalizzate, categorie e nomi delle pagine**: nessuna immagine o testo del fumetto. Le pagine non ancora verificate non entrano nel benchmark. Una pagina senza balloon può essere approvata intenzionalmente, come test di falsi positivi.

## Metriche di precisione e copertura

```powershell
comictranslate detector-eval "C:\fumetti\capitolo.cbr" "private_references\batman-annotations.json" --out "private_references\detection-report.json"
```

Il report restituisce:
- **Precisione = TP/(TP+FP)**: quota di balloon proposti corretti.
- **Recall = TP/(TP+FN)**: quota di balloon realmente presenti che sono stati ritrovati.
- **F1**: bilanciamento tra precisione e recall.
- **IoU ≥ 0,5**: criterio minimo di sovrapposizione geometrica fra poligono automatico e poligono verificato.
- **Recall per categoria** e accuratezza della categoria sui balloon localizzati.
- **Rischio fusione**: un poligono proposto ingloba almeno il 50% di **due o più** balloon verificati, ma non riceve più di un true positive.
- Indici delle regioni mancate e delle proposte erronee: sono dati utilizzabili per generare una coda di correzione.

I valori `null` indicano frazioni matematicamente non definite (per esempio nessuna proposta e nessuna regione reale), non uno zero silenzioso.

## Criterio di sviluppo

Non addestrare un detector sulle sole prime pagine. Prima annotare **5–11**, provare altri stili/colori/tipologie di balloon e tenere separate pagine di allenamento e di verifica. I riferimenti italiani servono principalmente a calibrare il *lettering*; le etichette del detector vanno disegnate sul CBR **inglese**, nelle sue coordinate reali.

Non condividere le scansioni commerciali su GitHub. La cartella `private_references/` è esclusa da Git.