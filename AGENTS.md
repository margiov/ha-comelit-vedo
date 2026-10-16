# AGENTS.md

Istruzioni per agenti AI e contributori su questo repository.

## Progetto

`ha-comelit-vedo` è una **custom integration per Home Assistant** (dominio
`comelit_vedo`) che controlla l'allarme delle centrali Comelit VEDO tramite il
**protocollo nativo** (TCP 10012 / TLS 10022), senza passare dall'interfaccia web.
Sostituisce la sola parte VEDO di integrazioni basate sul comando web.

Il codice del protocollo è in `custom_components/comelit_vedo/protocol.py`, adattato
dal progetto `comelit-vedo-client`.

## Struttura

- `custom_components/comelit_vedo/` — l'integrazione:
  - `protocol.py` — client nativo (solo stdlib), **bloccante**.
  - `coordinator.py` — `DataUpdateCoordinator`, esegue il protocollo in executor.
  - `config_flow.py` — configurazione da interfaccia (host, porta, unit_id, intervallo).
  - `alarm_control_panel.py` — un pannello per area (arma totale / disarma).
  - `binary_sensor.py` — un sensore per zona (aperta / a riposo + flag).

## Verifica

- Controllo sintassi: `python3 -m compileall custom_components`.
- Non c'è ancora una suite di test; le modifiche al protocollo vanno provate contro una
  centrale reale **partendo dalla sola lettura**.

## Sicurezza (importante)

- Opera su un **impianto d'allarme reale**. Il protocollo è bloccante: va SEMPRE
  eseguito in executor (`hass.async_add_executor_job`), mai nel loop asincrono.
- `unit_id` è una **credenziale**: non inserirla nel codice, non committarla, non
  inserirla nei log. Serve solo per arma/disarma.
- **Non committare mai** dati di un impianto reale (IP, unit_id, nomi zone/aree,
  catture `*.pcap`, `vedo.json`). Il repository deve restare generico.

## Convenzioni

- Codice e commenti in **italiano**, coerenti con lo stile esistente; nessuna
  dipendenza oltre Home Assistant e la libreria standard.
- Esegui i commit come `margiov <margiov@users.noreply.github.com>` e con nessun'altra
  identità o email.
- **Non** aggiungere righe di co-autore (es. `Co-Authored-By:`) di assistenti AI.

## Licenza

MIT (vedi `LICENSE`).
