# Morgenrapport

Automatisk morgenrapport som hver dag kl. 08:00 (norsk tid):

1. henter markedsdata (aksjeindekser, 10-årige statsrenter for USA/Norge/Sverige/Tyskland/UK, og Brent blend),
2. lager en pen HTML-rapport,
3. publiserer den på en nettside (GitHub Pages), og
4. sender den på epost til mottakerne dine – med lenke til nettsiden.

Alt kjører gratis i skyen via **GitHub Actions** – du trenger ikke ha PC-en på.

---

## Slik henger det sammen

```
GitHub Actions (cron 08:00)
        │
        ▼
  python -m src.main
   ├─ henter data        (src/fetch_data.py)
   ├─ lager HTML         (src/render.py + templates/report.html.j2)
   ├─ skriver nettside   (docs/index.html)  ──►  GitHub Pages (URL)
   └─ sender epost       (src/emailer.py via Resend)
```

Du redigerer normalt bare **`config.yaml`** (mottakere, avsender, nettside-URL).

---

## Engangsoppsett

Du gjør dette **én gang**. Sett av ca. 30 minutter. Trenger du hjelp underveis, si ifra så går vi gjennom det steget sammen.

### 1. Lag en GitHub-konto og last opp prosjektet
1. Opprett gratis konto på <https://github.com/signup>.
2. Last ned og installer **GitHub Desktop**: <https://desktop.github.com> (enklest når man ikke er utvikler).
3. I GitHub Desktop: **File → Add local repository** → velg mappa `C:\Users\JensMortenWembstad\Morgenrapport`.
   - Hvis den sier at mappa ikke er et repository: klikk **«create a repository»** i meldingen.
4. Klikk **Publish repository**. Anbefalt navn: `morgenrapport`. Velg **Public** – det kreves for at den gratis nettsiden (GitHub Pages) skal virke. Mottakernes epostadresser ligger *ikke* i repoet (de settes som en hemmelighet i steg 3b), så ingenting privat eksponeres.

### 2. Opprett Resend-konto og API-nøkkel (for epost)
1. Registrer deg gratis på <https://resend.com>.
2. Gå til **API Keys → Create API Key**. Kopier nøkkelen (den vises bare én gang).
3. **Avsenderdomene:**
   - **For å sende til flere/eksterne mottakere** må du verifisere et domene under **Domains → Add Domain** (krever at noen legger inn noen DNS-oppføringer for ditt eget domene – be IT om hjelp). Sett deretter `email_from` i `config.yaml` til f.eks. `Morgenrapport <morgenrapport@dittdomene.no>`.
   - **For en rask første test** kan du la `email_from` stå som `onboarding@resend.dev` – men da kan eposten kun sendes til din egen Resend-konto-epost.

### 3. Legg API-nøkkelen inn som GitHub-secret
1. Åpne repoet på github.com → **Settings → Secrets and variables → Actions**.
2. **New repository secret**:
   - Name: `RESEND_API_KEY`
   - Secret: lim inn nøkkelen fra Resend.
3. Klikk **Add secret**. (Nøkkelen blir aldri synlig i koden.)

### 3b. Legg mottakerne inn som GitHub-secret
For at private epostadresser ikke skal ligge i det offentlige repoet, settes mottakerne som en hemmelighet:
1. Samme sted: **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `RECIPIENTS`. Secret: epostadressene komma-skilt, f.eks. `en@epost.no, to@epost.no`.
3. Klikk **Add secret**. (Vil du endre mottakere senere, oppdaterer du bare denne hemmeligheten.)

### 4. Aktiver nettsiden (GitHub Pages)
1. I repoet: **Settings → Pages**.
2. Under **Build and deployment → Source**: velg **Deploy from a branch**.
3. Branch: **main**, mappe: **/docs**. Klikk **Save**.
4. Etter et par minutter får du en URL, typisk:
   `https://DITT-BRUKERNAVN.github.io/morgenrapport`

### 5. Fyll inn innstillinger i `config.yaml`
Åpne `config.yaml` og rediger:
- **`email_from`** – avsenderen (se steg 2).
- **`site_url`** – lim inn Pages-URL-en fra steg 4.

(Mottakerne settes som hemmeligheten `RECIPIENTS` i steg 3b, ikke her.)

Lagre, og i GitHub Desktop: skriv en kort melding og klikk **Commit to main → Push origin**.

### 6. Test at det virker
1. På github.com: gå til fanen **Actions → Morgenrapport → Run workflow** (manuell kjøring overstyrer klokkesperren).
2. Følg loggen. Når den er grønn: sjekk innboksen og åpne nettside-URL-en.

Ferdig! Fra nå går rapporten automatisk hver morgen kl. 08:00.

---

## Daglig bruk

- **Endre mottakere:** oppdater hemmeligheten `RECIPIENTS` (Settings → Secrets and variables → Actions). Ingen kodeendring nødvendig.
- **Endre avsender:** rediger `email_from` i `config.yaml`, og push endringen (GitHub Desktop: Commit → Push).
- **Endre hvilke indekser som vises:** rediger listen `indices` i `config.yaml`.
- **Se gamle rapporter:** de arkiveres under `docs/reports/ÅÅÅÅ-MM-DD.html` og er tilgjengelige på nettsiden.

---

## Teste lokalt på egen maskin (valgfritt)

```powershell
py -m pip install -r requirements.txt
py -m src.main --no-email      # lager docs/index.html uten å sende epost
```

Åpne deretter `docs/index.html` i nettleseren for å se resultatet.
For å også sende en testepost, sett nøkkelen først:

```powershell
$env:RESEND_API_KEY = "din-nokkel"
$env:FORCE_SEND = "1"
py -m src.main
```

---

## Feilsøking

| Symptom | Sjekk |
|---|---|
| Ingen epost kom | Er `RESEND_API_KEY` lagt inn som secret? Er avsenderdomenet verifisert i Resend? Sjekk Actions-loggen. |
| Workflow kjørte men sendte ikke | Klokkesperren: automatiske kjøringer sender kun kl. 08:00 Oslo. Bruk **Run workflow** for å teste når som helst. |
| Et tall mangler («–») | Datakilden var midlertidig utilgjengelig. Rapporten sendes likevel; tallet kommer normalt tilbake neste dag. |
| Nettsiden viser gammel rapport | Pages bruker 1–2 min på å oppdatere etter hver kjøring. |

---

## Filoversikt

| Fil | Hva det er |
|---|---|
| `config.yaml` | **Det du redigerer:** avsender, URL, indekser. (Mottakere settes som hemmelighet.) |
| `src/fetch_data.py` | Henter markedsdata fra kildene. |
| `src/render.py` + `templates/report.html.j2` | Lager HTML-rapporten. |
| `src/emailer.py` | Sender eposten via Resend. |
| `src/main.py` | Limet som binder alt sammen. |
| `.github/workflows/morgenrapport.yml` | Tidsplanen (kl. 08:00) i skyen. |
| `docs/` | Den publiserte nettsiden. |
