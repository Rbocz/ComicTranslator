ComicTranslator - versione Windows facile

1) Vai su https://github.com/Rbocz/ComicTranslator/actions/workflows/windows-portable.yml
2) Apri l'ultima esecuzione RIUSCITA (spunta verde).
3) In fondo scarica l'allegato "ComicTranslator-Windows-portatile".
4) Estrai completamente il file ZIP in una cartella sul PC (non avviare dal ZIP).
5) Doppio clic su ComicTranslator.exe (non richiede installazione di Python o 7-Zip).
6) Sfoglia, seleziona il CBR/CBZ, scegli la pagina 5 e premi "ANALIZZA I BALLOON".
7) Al primo utilizzo conferma il download del modello ONNX (richiede Internet).
8) Le proposte tratteggiate vanno CONTROLLATE e CORRETTE, quindi salva le annotazioni.

Il modello e i risultati privati restano in %LOCALAPPDATA%\ComicTranslator.
Il programma non carica le scansioni in rete. I modelli vengono scaricati
soltanto dopo il tuo consenso e verificati mediante SHA-256.

NOTA: Il programma e' un prototipo non firmato digitalmente; Windows potrebbe
mostrare un avviso SmartScreen. Scaricalo solo dalla tua repository ufficiale.
Se il modello non si scarica oppure un CBR non si apre, invia lo screenshot
dell'errore. Non e' ancora un traduttore automatico editoriale completo.

CBR: usa 7-Zip fornito nel pacchetto. 7-Zip e' un software terzo con licenze
LGPL/BSD e restrizioni unRAR: https://www.7-zip.org/license.txt.
Le comunicazioni sul software di terzi sono riportate nella cartella tools/.

Aggiornamento v0.6.1: corretto l'entrypoint dell'app compilata.
La pipeline Windows esegue ora un vero controllo di avvio del file ComicTranslator.exe
prima di pubblicare lo ZIP. Se hai scaricato la build precedente all'aggiornamento,
cancellala e usa la nuova build verificata.
