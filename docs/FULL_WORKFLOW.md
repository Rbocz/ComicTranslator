# Traduzione automatica di capitoli EN → IT (anteprima operativa)

## Flusso per Windows

1. Estrai il pacchetto Windows **interamente** sul secondo disco e apri `ComicTranslator.exe`.
2. Premi **Traduci fumetto completo**. Scegli CBR o CBZ, provider (Google Gemini / OpenAI), modello, cartella di uscita e inserisci la tua chiave API **nell'app**, non in chat.
3. Spunta il consenso all'invio delle pagine al provider e premi **TRADUCI TUTTO ED ESPORTA CBZ**. In modalità accurata vengono inviate fino a tre viste per pagina alta. Le chiamate API possono comportare addebiti.
4. Il risultato `*_ITALIANO.cbz`, il progetto modificabile `.project.json`, il rapporto `.report.json` e gli eventuali errori `.errors.json` sono salvati nella cartella scelta.
5. L'interfaccia permette di vedere le anteprime, correggere i testi, applicarli/rimuoverli e riesportare.

## Cosa fa realmente

- Legge il capitolo senza modificare l'archivio originale.
- Invia immagini compresse al provider scelto (su consenso), richiedendo OCR, traduzione contestuale in italiano e rettangoli stimati del testo e del contenitore.
- Valida geometrie, impaginazione e dimensioni; elabora pagina per pagina con checkpoint per riprendere senza ripetere le chiamate riuscite.
- Usa inpainting locale sulle **sole regioni ammesse** e lettering calcolato sui pixel della tavola; registra ciò che è stato inserito e ciò che è stato lasciato originale.
- Non memorizza la chiave API nel progetto né in un file di impostazioni. La digiti a ogni nuova sessione.

## Limitazioni e sicurezza

- La localizzazione dei balloon e delle righe è **una stima** del modello multimodale: non ha precisione editoriale garantita.
- Per evitare alterazioni permanenti del disegno, lo sfondo non sufficientemente chiaro/uniforme è lasciato originale. La percentuale di pagina tradotta può essere inferiore al 100%; il report elenca i blocchi non applicati.
- Traduzione e lettering automatici richiedono revisione umana su fumetti complessi, soprattutto balloon scuri, didascalie grafiche, onomatopee e piccoli caratteri.
- Le immagini delle tavole vengono inviate ai server dell'API scelta; verifica i termini di utilizzo e i diritti sulle opere.
- Senza chiavi API vere il pacchetto può essere verificato in locale e con test simulati, ma non è possibile certificare la qualità delle risposte live.
- Il programma non promette qualità editoriale perfetta né ricostruzione delle tavole colorate/integrate con l'illustrazione.

## Opzioni provider

- Gemini: preimpostazione `gemini-2.5-flash`, endpoint ufficiale GenerateContent con inline JPEG e JSON mode.
- OpenAI: preimpostazione `gpt-4.1-mini`, endpoint chat/completions vision e JSON mode.
- Non condividere mai chiavi API in GitHub, negli screenshot o nelle chat.

## Supporto

I moduli vecchi di annotation, benchmark e OCR rimangono disponibili nella repository per analisi e correzioni specialistiche, ma **non sono obbligatori** per usare il nuovo flusso automatico.