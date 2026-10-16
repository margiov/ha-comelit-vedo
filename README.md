# ha-comelit-vedo

Integrazione **custom per Home Assistant** che controlla l'allarme delle centrali
**Comelit VEDO** tramite il loro **protocollo nativo** (TCP 10012 in chiaro / 10022 TLS),
senza passare dall'interfaccia web della centrale.

> **Progetto non ufficiale.** Non affiliato né approvato da Comelit Group S.p.A.
> Il protocollo è stato ricostruito tramite reverse engineering a scopo di
> interoperabilità. Opera su un impianto d'allarme reale: usalo a tuo rischio.

## Perché

L'inserimento via interfaccia web manda alla centrale un comando "forzato" per una
singola area, e in alcune centrali questo finisce per coinvolgere anche altre aree.
Il protocollo nativo usa invece un **vettore esplicito con un valore per ogni area**
(inserisci / disinserisci / non toccare): le aree non indicate restano invariate.

## Cosa fornisce

- Un **pannello d'allarme** (`alarm_control_panel`) per ogni area presente:
  inserimento totale (`arm_away`), parziale P1 (`arm_home`) e P2 (`arm_night`), e
  disinserimento. Non richiede codice.
- Un **sensore binario** (`binary_sensor`) per ogni zona presente: attiva / a riposo,
  con i flag (esclusa, guasto, manomissione, batteria…) come attributi. Il tipo
  predefinito è *movimento*; per i contatti porta/finestra cambialo da HA
  (impostazioni dell'entità → "Mostra come").
- Nomi di aree e zone letti automaticamente dalla centrale.
- Configurazione da interfaccia (config flow).

## Requisiti

- Home Assistant 2024.11 o successivo.
- Una centrale Comelit VEDO con modulo IP raggiungibile in rete locale.
- `unit_id` dell'installazione: **solo** per inserire/disinserire. Senza, l'integrazione
  funziona in sola lettura (stato di aree e zone). Vedi
  [comelit-vedo-client](https://github.com/margiov/comelit-vedo-client) per come ricavarlo.

## Installazione (HACS)

1. HACS → Integrazioni → menu → *Custom repositories*.
2. Aggiungi `https://github.com/margiov/ha-comelit-vedo` come categoria *Integration*.
3. Installa "Comelit VEDO (nativo)" e riavvia Home Assistant.
4. Impostazioni → Dispositivi e servizi → *Aggiungi integrazione* → "Comelit VEDO".

In alternativa, copia `custom_components/comelit_vedo/` nella cartella
`config/custom_components/` di Home Assistant e riavvia.

## Configurazione

| Campo | Note |
|---|---|
| Indirizzo IP | IP del modulo IP della centrale. |
| Porta | `10022` (TLS, consigliata) o `10012` (in chiaro). |
| `unit_id` | Hex. Solo per arma/disarma; lascialo vuoto per la sola lettura. |
| Intervallo | Secondi tra un aggiornamento e l'altro (default 15). |

La centrale risponde solo alle richieste, quindi lo stato è aggiornato a ogni
interrogazione (polling locale).

## Limiti noti

- Inserimenti supportati: **totale** (`arm_away`), **parziale P1** (`arm_home`) e
  **parziale P2** (`arm_night`); il disinserimento è totale. I codici parziali
  derivano dall'enum `AreaActivation` dell'app (totale/disinserimento verificati su
  cattura, P1/P2 non ancora verificati su campo).
- Lo stato riflette tutte le condizioni della centrale: `disarmed`, `arming` (tempo
  di uscita), `armed_away`/`armed_home`/`armed_night`, `pending` (tempo di ingresso),
  `triggered`. Gli attributi riportano `alarm_memory`, `not_ready`, `sabotage`,
  `anomaly`, `exclusion`, `open_zone`, `output_on`.
- Lo stato zone copre le prime 30 posizioni zona.
- TLS cifra il trasporto ma non aggiunge autenticazione.

## Sicurezza

- `unit_id` è una credenziale: chi la conosce e raggiunge la centrale può inserire e
  disinserire le aree. Non condividere la configurazione.
- Ogni comando apre una sessione che la centrale registra nel log eventi.

## Licenza

[MIT](LICENSE) © 2026 margiov.
