# Rilevamento avanzato senza ridisegnare ogni balloon

Questa modifica introduce tre componenti sperimentali:

1. **Analisi a più scale**: un'inferenza sull'intera pagina più quattro ritagli sovrapposti sulle pagine grandi. Cerca testi piccoli che si perdono nel ridimensionamento a 640×640, ma richiede più tempo.
2. **Contorni stimati**: OpenCV tenta di recuperare una forma luminosa chiusa intorno a un box del detector. Verde = contorno approssimativo; azzurro = rettangolo; arancione = testo esterno. Se il contorno non è sufficientemente affidabile, conserva il rettangolo.
3. **Usa suggerimenti come BOZZA**: consente di correggere solo gli errori, senza ricopiare ogni regione, mantenendo la pagina NON verificata.

Le etichette tecniche ora sono nascoste per impostazione predefinita.

**Limiti:** le proposte non sono maschere adatte a cancellare testo o geometrie definitive per il lettering. Non sono ground truth. Forme colorate, aperte e sovrapposte richiedono altri modelli.

Su 10 aree testuali individuate manualmente nella pagina 5 privata, il raffinamento ha ottenuto 6 contorni candidati e 4 fallback rettangolari. Non è una misura di recall del detector né di accuratezza dei contorni: l'inferenza ONNX reale non è stata effettuata in questo benchmark geometrico.

Prossimo passo: valutare il recall del detector reale e la precisione dei contorni su annotazioni complete, e solo successivamente sviluppare maschere di pulizia verificabili. Nessuna tavola privata è nella repository.
