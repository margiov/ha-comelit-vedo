# Icona del brand

Home Assistant mostra l'icona di un'integrazione prendendola dal repository
ufficiale [home-assistant/brands](https://github.com/home-assistant/brands),
non dai file dell'integrazione. Finché il dominio `comelit_vedo` non è lì, la
card in *Impostazioni → Dispositivi e servizi* mostra l'icona generica: è normale
per le integrazioni custom.

Qui sono pronti gli asset (icona scudo, sfondo trasparente):

- `custom_integrations/comelit_vedo/icon.png` — 256×256
- `custom_integrations/comelit_vedo/icon@2x.png` — 512×512

## Come farla comparire (una volta sola)

1. Fai un fork di `home-assistant/brands`.
2. Copia la cartella `custom_integrations/comelit_vedo/` di questo repo nella stessa
   posizione del fork.
3. Apri una pull request su `home-assistant/brands`.
4. A PR unita, l'icona compare in HA (serve poi svuotare la cache del browser).

Le icone devono essere PNG quadrate, a sfondo trasparente e ritagliate al contenuto;
quelle qui incluse rispettano le dimensioni richieste (256 e 512). Sostituiscile pure
con un'immagine diversa mantenendo nomi e dimensioni.
