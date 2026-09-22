# fishing_ai

Django-projekti, jossa on fishinglog-sovellus ja SQLite-tietokanta. Ei AI-ominaisuuksia.

## Käynnistys (PowerShell projektikansiossa)

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

Jos aktivointi on estetty, käytä suoraan virtuaaliympäristön Pythonia:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Avaa http://127.0.0.1:8000/. Sammuta palvelin painamalla Ctrl+C.

## Uusi ympäristö (Python asennettuna)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Tietokanta on db.sqlite3. Asetukset ovat paikallista kehitystä varten.

## Fishing Log

Etusivu: http://127.0.0.1:8000/
Reissulista: /reissut/
Uusi reissu: /reissut/uusi/
Reissun tiedot: /reissut/<id>/
Muokkaus ja poisto: /reissut/<id>/muokkaa/ ja /reissut/<id>/poista/
Uusi saalis: /reissut/<id>/saaliit/uusi/
Saaliin muokkaus ja poisto: /reissut/<id>/saaliit/<saalis_id>/muokkaa/ ja /poista/

Reissulle tallennetaan päivämäärä, järvi, paikka, ajat, sää, lämpötilat,
kalastustapa, syvyys, veneen nopeus ja muistiinpanot. Saaliita voi lisätä useita.
Mittaustiedot ovat vapaaehtoisia. Syvyys on metreinä ja nopeus km/h.
Aloitusaikaa aikaisempi lopetusaika tarkoittaa seuraavaa päivää.
Reissun poistaminen poistaa myös sen saaliit; poistot vaativat vahvistuksen.
Kieli on suomi ja aikavyöhyke Europe/Helsinki. SQLite säilyy käytössä.

Bootstrap 5.3.8 ladataan jsDelivr-CDN:stä, joten Bootstrap-ulkoasu tarvitsee
selaimelta verkkoyhteyden. Omat tyylit ovat fishinglog/static/fishinglog/style.css.
Bootstrapin dokumentaatio: https://getbootstrap.com/docs/5.3/getting-started/introduction/

## Tarkistukset

```powershell
python manage.py migrate
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
```

Automaattiset testit kattavat sivut, CRUD-toiminnot, useat saaliit,
syötteiden validoinnin, poistovahvistukset, CSRF-suojauksen, väärät tunnisteet,
sivutuksen ja yön yli kestävän reissun. Testit käyttävät erillistä testitietokantaa.


## Automaattinen säähaku

Syötä reissun päivämäärä, aloitusaika ja kalastuspaikka ja paina **Hae sää**.
Säähaun paikka -kentällä voi tarkentaa haun paikkakuntaan (esim. Savonlinna)
tai koordinaatteihin muodossa leveysaste, pituusaste (esim. 61.87, 28.88).
Paikannimet ratkaisee FMI; vapaa paikallinen nimi kuten "oma laituri" ei välttämättä löydy.

Haku täyttää ilman lämpötilan, tuulen nopeuden (m/s), suunnan (asteet),
ilmanpaineen (hPa), pilvisyyden (%) ja tunnin sateen (mm), kun ne ovat saatavilla.
Arvoja voi muokata ja ne tallentuvat vasta Tallenna-painikkeella. Veden lämpötila ja muut reissutiedot säilyvät ennallaan. Sääkuvaus voidaan nyt täyttää sääarvoista muodostetulla yhteenvedolla. Haun aikana muutettua
paikkaa/ajankohtaa ei hyväksytä vanhan tuloksen kohteeksi eikä haun aikana
käsin muokattuja sääkenttiä ylikirjoiteta. Virhe tai puuttuva mittaus ei tyhjennä kenttiä.

### Tietolähde ja ajankohdat

- FMI WFS: https://opendata.fmi.fi/wfs (HTTPS, ei API-avainta).
- Havainnot: fmi::observations::weather::timevaluepair.
- Ennuste: fmi::forecast::edited::weather::scandinavia::point::timevaluepair.
- Menneille ajoille haetaan havaintoja. Vain viimeisen kolmen tunnin tyhjä
  havaintotulos voi vaihtua ennusteeksi, joka merkitään selvästi ennusteeksi.
- Tuleville ajoille haetaan FMI:n virallista ennustetta, yleensä noin 10 päiväksi.
  Ennustejakson ulkopuolella annetaan ilmoitus; vanhaa ennustetta ei esitetä uutena.
- Käyttäjän ajat ovat Europe/Helsinki-aikaa, rajapinnan ajat UTC-aikaa.
  Kellonsiirron puuttuvat tai moniselitteiset ajat hylätään ymmärrettävällä virheellä.
- Kullekin kentälle valitaan lähin kelvollinen mittaus enintään tunnin etäisyydeltä.
  Havaintojen saatavuus riippuu asemasta ja vuodesta. Kaikkia mittauksia ei aina saada.
- Paikannimelle FMI valitsee lähiaseman 50 km säteellä. Koordinaateille haetaan
  rajatulta alueelta ja valitaan lähin dataa sisältävä asema enintään 50 km päästä.
  Eri asemien mittauksia ei yhdistetä. Lähde, asema/piste ja ajat näytetään ja tallennetaan.
- Havaintopilvisyys n_man muunnetaan kahdeksasosista prosenteiksi; 9 (taivas
  peittynyt) jätetään puuttuvaksi. NaN, äärettömät ja virheelliset negatiiviset arvot
  eivät täytä kenttiä. Nolla on kelvollinen mittaus.
- Sade on haetun ajankohdan tuntimäärä, ei koko reissun kertymä.
- Onnistuneita hakuja pidetään välimuistissa 5 minuuttia. Verkkopyynnöillä on
  aikarajat, vastauksen kokoraja ja turvallinen XML-jäsennys. HTTPS-varmenteet tarkistetaan.

Dokumentaatio:
https://en.ilmatieteenlaitos.fi/open-data-manual-time-series-data
https://en.ilmatieteenlaitos.fi/open-data-changelog
https://en.ilmatieteenlaitos.fi/open-data-manual-wfs-examples-and-guidelines

### Säähaun asennus ja testaus

Uudet riippuvuudet: requests ja defusedxml (versiot requirements.txt-tiedostossa).

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py test
```

64 Django-testiä kattaa nykyiset CRUD-toiminnot sekä säähaun jäsennyksen,
yksikkömuunnokset, puuttuvat arvot, aikavalinnan, ennusteeseen siirtymisen,
aikavyöhykkeen, koordinaatit, verkkovirheet, syötteet, CSRF:n ja muokattujen
säätietojen tallentamisen. Automaattiset testit eivät tarvitse verkkoyhteyttä.

Toteutusta kokeiltiin myös oikealla FMI-datalla nykyhetkelle, seuraavalle päivälle,
vuodelle 2020 ja koordinaateille. Selaimessa varmistettiin Hae sää -painikkeen
havainto- ja ennustehaku, kenttien täyttyminen, käsin muokkaus ja paikkahaun virhetila.

Jos portissa 8000 on vanha palvelin, käynnistä päivitetty versio vapaaseen porttiin:

```powershell
python manage.py runserver 127.0.0.1:8002
```

Avaa http://127.0.0.1:8002/. Palvelin tarvitsee verkkoyhteyden FMI:hin.


## Usean saaliin tallennus ja saaliittomat reissut

Reissun **Lisää saalis** -sivulla näkyy aluksi yksi kalalomake.
**+ Lisää kala** lisää uuden ja **Poista kala** poistaa kyseisen tallentamattoman
lomakkeen. **Tallenna saaliit** tarkistaa kaikki lomakkeet ja tallentaa kalat
samassa tietokantatransaktiossa. Jos jonkin kalan tiedot ovat virheelliset,
yhtään kalaa ei tallenneta ja syötetyt tiedot jäävät korjattaviksi.
Yhden pyynnön suojaraja on 1000 kalalomaketta; lisää eriä voi tallentaa samalle reissulle.

**Ei saalista** löytyy sekä reissun luonti-/muokkauslomakkeelta että saaliiden
lisäyssivulta. Valittuna kalalomakkeita ei tarvitse täyttää eikä niitä tallenneta.
Merkintä näkyy reissun tiedoissa ja reissulistalla. Merkinnän voi poistaa reissua
muokkaamalla tai lisäämällä myöhemmin kalan (poista silloin rasti lisäyssivulla).
Olemassa olevia saaliita ei poisteta saaliittomuusvalinnalla: ristiriitaisesta
valinnasta annetaan virhe. Viimeisen kalan poistaminen ei automaattisesti tarkoita,
että reissu olisi merkitty saaliittomaksi.

### Pituuden ja painon yksiköt

Pituus tallennetaan metreinä ja paino kiloina DecimalField-kenttiin, kolmen
desimaalin tarkkuudella. Esimerkiksi **0,45 m** ja **1,25 kg**. Sekä pilkku että
piste käyvät pituuden, painon ja syvyyden syötteissä. Tyhjät mittaukset säilyvät
tyhjinä, eivät nollina. Syvyyden tarkkuus säilyy yhdessä desimaalissa.

Migraatio 0003 muuntaa vanhat pituudet jakamalla sadalla ja painot jakamalla
tuhannella; esimerkiksi 52,5 cm -> 0,525 m ja 1501 g -> 1,501 kg.
Tietokantasarakkeet ovat length_m ja weight_kg; Python-kenttien nimet säilyvät
length ja weight. No_catch on oletuksena False, joten vanhoja reissuja ei
päätellä saaliittomiksi pelkän puuttuvan saaliskirjauksen perusteella.

Lisätyt testit kattavat usean kalan tallennuksen, desimaalipilkun, virheelliset
lomakkeet, atomisuuden myös tietokantavirheessä, saaliittomuuden, myöhemmän
saaliin lisäämisen sekä tietomigraation (myös puuttuvat arvot, nollat ja palautus).
Kaikki 64 Django-testiä ajetaan komennolla python manage.py test.


## Automaattisen säähaun täydennys

Kun päivämäärä, aloitusaika ja paikka on täytetty, haku alkaa automaattisesti
kentän muokkauksen valmistuttua (800 ms viive). Automaattihaun voi poistaa
valinnasta. Hae sää -painike säilyy käytössä. Olemassa olevia tai käsin
muokattuja arvoja ei ylikirjoiteta automaattihaussa; painike päivittää ne.
Haun aikana tehdyt käsinmuokkaukset säilyvät myös painikehaussa.
Vanhan pyynnön vastaus ei täytä lomaketta paikan tai ajan muuttumisen jälkeen.
Reissun tallentaminen ei odota säähakua eikä tarvitse onnistunutta säähakua.

Lisätty wind_gust (m/s), latitude ja longitude (5 desimaalia), migraatiossa 0004.
Tuulen asteista esitetään myös kahdeksan pää-/väli-ilmansuunnan mukainen nimi.
Sääkuvaus on pilvisyydestä ja tunnin sateesta muodostettu, sellaiseksi merkitty
yhteenveto; se ei ole erillinen havaittu sääilmiökoodi. Puuskat haetaan parametrilla
wg_10min havainnoista ja WindGust ennusteesta. Ennusteesta puuska voi puuttua;
silloin käyttäjä saa ilmoituksen eikä kenttään keksitä arvoa.

Kangasniemi ja Jyväskylä ratkaistaan FMI:n /timeseries-paikkahaulla.
Kyyvesi puuttuu FMI:n paikannimihausta, joten sille käytetään paikallisesti
varmennettua järven edustavaa pistettä: 61.99757, 27.16802.
Lähde: https://www.openstreetmap.org/relation/303354
© OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright
Sovellus ei käytä yleistä julkista Nominatim-paikkahakua.
Nimillä tehdyt FMI-paikkahaut säilyvät välimuistissa vuorokauden.

Tallennettavat koordinaatit ovat haetun paikan edustava piste tai käyttäjän
antamat koordinaatit. Havaintoaseman koordinaatit pysyvät erikseen lähdetekstissä.
Käyttäjä voi tarkistaa ja korjata koordinaatit. Tarkkaan koordinaattipohjaiseen
säähakuun annetaan leveysaste,pituusaste Säähaun paikka -kentässä.

Testit:

```powershell
python manage.py test
node --test fishinglog/js_tests/weather.test.cjs
```

64 Django-testiä ja 15 JavaScript-testiä. Mukana paikkahaun virhevastaukset,
verkkovirhe, säättömän reissun tallennus, koordinaatit, puuskat, ilmansuunnat,
automaattitäyttö, käsinmuokkausten suojaus ja vanhan vastauksen hylkääminen.
Selaimessa varmistettu Kyyveden automaattihaku ilman painiketta sekä painikehaun
virheilmoitus ja käsin muokattujen arvojen säilyminen. FMI-livehaku testattu myös
Kangasniemen ennusteelle ja Jyväskylän vuoden 2020 havainnoille.


## Tarkka kalastuspaikka kartalta

Reissun lisäys- ja muokkaussivuilla on Leaflet 1.9.4 -kartta ja OpenStreetMap-
karttapohja. Napauta karttaa tai siirrä merkkiä vetämällä. Koordinaatit näkyvät
lomakkeella ja tallentuvat Tallenna-painikkeesta. Valmiiksi tallennettu piste
näytetään markerilla; ilman tarkkaa pistettä kartta voi keskittyä säähaun alueelle,
mutta se ei luo merkkiä eikä valitse kalastuspaikkaa automaattisesti.

Käytä nykyistä sijaintiani pyytää selaimen sijaintiluvan vasta painettaessa.
Luvan epääminen, paikannuksen aikaraja ja puuttuva geolocation käsitellään
ilmoituksella. Paikannus vaatii selaimen tukeman suojatun ympäristön: HTTPS tai
localhost. Puhelimen HTTP-yhteys tietokoneen lähiverkko-osoitteeseen ei yleensä
salli paikannusta; karttapisteen voi silloin valita käsin.

Tietosivulla näytetään pieni kartta ja Avaa kartalla -linkki OpenStreetMapiin,
jos tarkka piste on tallennettu. Kartan käyttö ja paikannus eivät muuta järven
nimeä, kalastuspaikan nimeä tai säähaun nimeä. Sääaseman tiedot säilyvät lähdetekstissä.

Tietomalli ja migraatio 0005:
- latitude/longitude: vain käyttäjän valitsema tarkka kalastuspaikka.
- weather_latitude/weather_longitude: säähaun käyttämän paikan koordinaatit.
- weather_source: havainto-/ennustelähde, sääasema/piste ja ajat ennallaan.
- Vanhat latitude/longitude-sarakkeet nimetään säähaun koordinaateiksi, ja uudet
  tarkat koordinaatit alkavat tyhjinä. Vanhaa paikkakunnan/järven edustavaa pistettä
  ei tulkita tarkaksi kalastuspaikaksi. Vanhojen reissujen karttapiste valitaan käsin.

Säähaku käyttää ensisijaisesti tarkan kalastuspaikan molempia koordinaatteja.
Ilman niitä käytetään säähaun paikkatietoa kuten ennenkin. Pelkkä yksi koordinaatti
antaa virheilmoituksen. Säähaun vastaus ei koskaan muuta tarkkoja koordinaatteja.
Poista tarkka sijainti tyhjentää valinnan lomakkeelta, ja muutos vahvistetaan tallentamalla.

Leaflet ja sen kuvat/lisenssi ovat paikallisesti static/fishinglog/leaflet-kansiossa.
Karttatiilet tulevat suoraan https://tile.openstreetmap.org-palvelusta eikä maksullista
API-avainta tarvita. Näytetään OSM-attribuutio, lähetetään origin-Referer ja käytetään
selaimen normaalia välimuistia. Tiiliä ei esiladata eikä offline-latausta tarjota.
Karttapohjan saatavuus riippuu verkkoyhteydestä ja OSM-palvelusta.
Dokumentaatio: https://leafletjs.com/examples/quick-start/
OSM-käyttöehdot: https://operations.osmfoundation.org/policies/tiles/

Kaikki testit:

```powershell
python manage.py test
node --test fishinglog/js_tests/weather.test.cjs fishinglog/js_tests/map.test.cjs
```

64 Django-testiä ja 15 JavaScript-testiä kattavat myös koordinaattien migraation,
karttapisteen muokkauksen, nollakoordinaatit, säähaun prioriteetin, markerin siirron,
paikannuksen onnistumisen/epäämisen ja myöhäisen paikannusvastauksen hylkäämisen.
Selaimessa tarkistettu karttaklikkaus, markerin veto, mobiiliasettelu ja FMI-haku
karttapisteestä. Todellista käyttäjän sijaintilupaa ei tarvittu testaukseen.


## Käyttäjät ja kirjautuminen

Kirjautuminen: `/kirjaudu/`, rekisteröityminen: `/rekisteroidy/`.
Uloskirjautuminen tapahtuu yläpalkin POST-painikkeella.
Reissut ja saaliit näkyvät vain reissun omistajalle. Myös säähaku vaatii kirjautumisen.

Migraatio 0006 säilyttää vanhat reissut ja saaliit suljetulla
`fishingai_legacy`-tilillä (tarvittaessa numeroitu nimi). Tilillä ei voi kirjautua.
Rekisteröityminen ei anna automaattisesti pääsyä vanhoihin tietoihin.
Kun oikea käyttäjä on rekisteröitynyt, ylläpitäjä voi siirtää vanhat reissut:

```powershell
python manage.py assign_legacy_trips OMA_KAYTTAJANIMI
```

Tarvittaessa lähdetilin voi antaa muodossa `--from-user fishingai_legacy_1`.
Komento säilyttää reissujen saaliit, säätiedot ja koordinaatit.
Tilin poistaminen poistaa myös omat reissut ja saaliit (migraatio 0009).


## Kalastusavustaja

Sivu `/avustaja/` vaatii kirjautumisen. Lähetä-painike tekee enintään yhden
OpenAI Responses API -kutsun (1100 vastaustokenia). Kysymyksen ajankohta ja
paikka tulkitaan paikallisilla säännöillä; tarkenna paikka lomakkeen kenttään tarvittaessa. Oletusmalli on `gpt-4.1-mini`.
Mallin voi vaihtaa `OPENAI_MODEL`-ympäristömuuttujalla yhteensopivaan malliin.
Toteutus käyttää olemassa olevaa requests-kirjastoa.

API-avain luetaan ainoastaan `OPENAI_API_KEY`-ympäristömuuttujasta.
`.env.example` on avaimeton esimerkki; sovellus ei lataa `.env`-tiedostoa automaattisesti.
Aseta avain samassa PowerShellissä, jossa käynnistät palvelimen:

```powershell
$assistantSecret = Read-Host "OpenAI API-avain" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $assistantSecret).Password
.\.venv\Scripts\python.exe manage.py runserver
```

Avain ei tule komentohistoriaan. Muuttuja koskee tätä PowerShell-istuntoa ja sen
käynnistämiä prosesseja. Käynnistä palvelin uudelleen avaimen asettamisen jälkeen.
Tarvitset OpenAI API -avaimen ja API-käyttöä varten käyttövaraa/kiintiötä.
Älä kirjoita avainta lähdekoodiin tai commitoi paikallista `.env`-tiedostoa.

OpenAI saa kysymyksen sekä enintään 40 uusimman oman reissun yhteenvedon,
enintään 8 saalisryhmää reissulta. Historiayhteenveto rajataan 22 000 merkkiin.
Käyttäjätunnusta, salasanaa ja vapaita reissujen/saaliiden muistiinpanoja ei lähetetä.
Vastauksia ei tallenneta sovelluksen tietokantaan; API-pyynnössä `store=false`.
Kysymykset ja valittu sääpaikka välitetään tarpeen mukaan ulkoisille palveluille.

Sää tulee FMI:ltä. Kysymyksen paikka ohittaa lomakkeen paikan; niiden puuttuessa
käytetään viimeisintä sopivaa omaa reissua, ensisijaisesti sen GPS-koordinaatteja.
Ajanjaksot: nyt, tänään, huomenna, seuraavat kolme kalenteripäivää (tämä päivä mukana).
Ennusteita verrataan kolmen tunnin välein Suomen ajassa. Yksi WFS-pyyntö kattaa
koko vertailun. Paras aika tarkoittaa parasta saatavilla olevan otoksen aikaa.
Sääkatkossa lähtöpisteytystä ei näytetä. Historiakysymys ei hae uutta säätä.
Arvio on epävarma, eikä saalismäärien korrelaatio todista syy-yhteyttä.

Testit käyttävät simuloituja OpenAI-vastauksia, eivätkä kuluta API-kiintiötä.
API- ja Structured Outputs -ohjeet:
https://developers.openai.com/api/docs/guides/structured-outputs


Avustajan käyttöraja on 10 OpenAI HTTP-kutsua käyttäjää kohti liukuvan tunnin
sisällä. Puuttuva avain, lomakevirhe ja ennen HTTP-kutsua keskeytyvä käsittely
eivät kuluta kiintiötä. Kiintiö kirjataan atomisesti juuri ennen HTTP-lähetystä.
Lähetetyn pyynnön virhe tai timeout lasketaan, koska palvelin on voinut vastaanottaa pyynnön. Käyttölaskuri ja päällekkäisen
pyynnön esto ovat tietokannassa; niihin tallennetaan vain käyttäjäviite,
aikaleimat ja lukituksen versio, ei kysymystä, vastausta tai API-avainta.
Käyttörajan tarkistuksen epäonnistuessa API:a ei kutsuta. OpenAI-pyynnön timeout
on 30 sekuntia (requests-yhteys/lukuaikakatkaisu), eikä automaattisia uusintayrityksiä ole.


## Railway-tuotantoon valmistelu

Projektin juuri on kansio, jossa ovat `manage.py`, `requirements.txt` ja `railway.json`.
Kun GitHub-repossa nämä ovat juuressa, Railwayn Root Directory on `/`.
Paikallinen `python manage.py runserver` käyttää edelleen SQLitea, ellei DATABASE_URL ole asetettu.
`.env.example` on dokumentaatio; `.env`-tiedostoa ei lueta automaattisesti.

1. Luo Railway-projektiin PostgreSQL-palvelu ja GitHub-repoon yhdistetty Django-palvelu.
2. Lisää Django-palveluun alla olevat muuttujat. Luo sille julkinen HTTPS-domain ja
   lisää juuri tämä domain sallittuihin hosteihin sekä CSRF-origineihin.
3. Railway käyttää `railway.json`-tiedostoa: build ajaa `collectstatic --noinput`,
   pre-deploy ajaa `migrate --noinput`, ja käynnistys ajaa Gunicornin portissa `$PORT`.
   Migraatioita ei ajeta jokaisessa Gunicorn-workerissa. Epäonnistunut migraatio estää
   uuden version käynnistyksen. Älä käynnistä samanaikaisia migraatioajoja.
4. Ota tietokantavarmuuskopio ennen myöhempiä skeemamuutoksia. Pre-deploy-migraatio
   muuttaa yhteistä tietokantaa ennen liikenteen siirtymistä: käytä jatkossa taaksepäin
   yhteensopivia migraatioita. Älä muokkaa jo ajettuja migraatiotiedostoja.
5. Varmista deployn jälkeen kirjautuminen, rekisteröityminen, kartta, sää, staattiset
   tiedostot ja omistajarajaukset. AI:n oikea kokeilu tehdään erikseen API-avaimella.

| Muuttuja | Railway-arvo |
| --- | --- |
| `DJANGO_ENV` | `production` |
| `DEBUG` | `False` |
| `DJANGO_SECRET_KEY` | Pitkä satunnainen salainen avain, sama kaikille workereille ja uudelleenkäynnistyksille |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (vaihda Postgres oman tietokantapalvelun nimeksi) |
| `ALLOWED_HOSTS` | `oma-palvelu.up.railway.app` ilman protokollaa; useat pilkulla eroteltuina |
| `CSRF_TRUSTED_ORIGINS` | `https://oma-palvelu.up.railway.app`; useat pilkulla eroteltuina |
| `OPENAI_API_KEY` | Oma OpenAI API-avain; tarvitaan vain Kalastusavustajan käyttöön |
| `OPENAI_MODEL` | Valinnainen, oletus `gpt-4.1-mini` |

Railway asettaa `PORT`-muuttujan. PostgreSQL-yhteys käyttää DATABASE_URL:n SSL-asetuksia;
Railwayn sisäinen tietokantaosoite toimii Railway-verkon sisällä. Älä kopioi oikeaa
DATABASE_URL-arvoa lokiin, README:hen tai Git-repoon.

Tuotannossa puuttuva Django-avain, PostgreSQL-osoite tai host-lista estää käynnistyksen.
Railway tunnistetaan myös `RAILWAY_ENVIRONMENT_ID`-muuttujasta: DEBUG=True estetään.
HTTPS-proxya varten käytetään X-Forwarded-Proto-otsaketta, suojattuja evästeitä,
HTTPS-uudelleenohjausta ja HSTS:ää. Ali-domainien HSTS ja preload eivät ole käytössä;
`check --deploy` ilmoittaa niistä kaksi tarkoituksellista varoitusta. Niitä ei aktivoida
ennen oman domainin kaikkien alidomainien HTTPS-valmiuden varmistusta.

WhiteNoise tarjoaa collectstatic-kansion pakatut ja sisällön perusteella nimetyt tiedostot.
`staticfiles/`, `.env`, `.django-secret-key` ja SQLite-tiedostot ovat Gitin ulkopuolella.
Tuotannossa Django-avain ei koskaan tule paikallisesta avaintiedostosta.
OPENAI_API_KEY luetaan edelleen vain prosessin ympäristöstä; avaimen kyllä/ei-teksti
poistettiin käyttöliittymästä. Diagnostiikkakomento on käytettävissä vain palvelimen komentoriviltä.

Paikallista SQLite-dataa ei siirretä automaattisesti uuteen PostgreSQL-tietokantaan.
Vanhojen käyttäjien ja reissujen siirto on tehtävä erillisenä varmuuskopioituna työnä.
Nykyinen kirjautuminen ei lähetä sähköpostia. Tuotannon SMTP-backendille pitää määrittää
palvelu erikseen, jos sähköpostitoimintoja lisätään myöhemmin.

Tarkistukset: `python manage.py test`, `python manage.py check`,
`python manage.py collectstatic --noinput` ja tuotantoasetuksilla `python manage.py check --deploy`.
Gunicorn on Railwayn Linux-palvelinta varten; Windows-kehityksessä käytetään runserveriä.
Ohjeet: https://docs.railway.com/guides/django ja
https://whitenoise.readthedocs.io/en/stable/django.html


## Profiili ja käyttäjätilin hallinta

`/profiili/` näyttää oman käyttäjänimen ja muokattavan sähköpostin. Käyttäjänimi säilyy.
Djangon salasananvaihto `/profiili/salasana/` tarkistaa nykyisen salasanan ja säilyttää
kirjautumisen. `/profiili/poista/` vaatii POST-lähetyksen, nykyisen salasanan sekä
vahvistusruudun. Poisto hävittää tilin omat reissut, saaliit, kalastusprofiilin ja
avustajan käyttölaskurin atomisesti. GET-pyyntö ei poista mitään.

`/admin/` käyttää Django-authin ylläpito-oikeuksia. Kalastusmallien hallinta on rajattu
superkäyttäjille, ja listoissa näkyvät omistajat. Käyttäjät ovat Djangon UserAdminissa.
Ylläpitotunnuksen voi luoda palvelimen komentorivillä: `python manage.py createsuperuser`.


## Yksityiset saaliskuvat ja Railway Volume

Kuvat ovat vapaaehtoisia. JPEG, PNG ja WebP hyväksytään (enintään 8 Mt / kuva,
24 megapikseliä, enintään 20 tiedostoa / lomakelähetys). Pillow tarkistaa sisällön,
korjaa EXIF-kierron ja tallentaa enintään 1600 × 1600 pikselin JPEG-kuvan uusista
pikseleistä. EXIF/GPS, muut metatiedot ja alkuperäinen tiedostonimi poistetaan.
HEIC/SVG/GIF eivät ole tuettuja: muunna tarvittaessa JPEG-muotoon.

Paikallisesti tiedostot tallentuvat MEDIA_ROOTiin (`media/catches/`), joka on
.gitignoressa. MEDIA_URL `/private-media/` on tarkoituksella **ilman julkista
palvelureittiä**. Kuvia ei saa tarjoilla static()-reitillä, WhiteNoisella, nginxillä
julkisesti tai avoimen bucketin URLilla. Käytä aina `/saaliit/<id>/kuva/`-reittiä:
se vaatii kirjautumisen ja tarkistaa `trip.owner == request.user` jokaisella
pyynnöllä. Vastauksessa on private/no-store sekä nosniff. Myös admin käyttää samaa
omistajuusrajausta kuvien hakemiseen. Kuvan vaihto, poisto ja saaliin/reissun/tilin
poisto poistavat vanhan tiedoston vasta tietokantatransaktion onnistuttua.

### Ennen tuotannon kuvalatausten käyttöönottoa (manuaalisesti)

1. Liitä Railwayn **Django-webpalveluun** pysyvä Volume, esimerkiksi mount-polkuun
   `/data`. PostgreSQL-palvelun oma levy ei riitä. Tässä muutoksessa ei luoda levyä,
   hankita palvelua eikä käytetä uutta API-avainta. Tarkista oman Railway-tilauksesi
   levykiintiö ja kustannukset ennen Volumen luontia.
2. Railway asettaa `RAILWAY_VOLUME_MOUNT_PATH`-muuttujan automaattisesti runtimeen.
   Älä lisää muuttujaa käsin korvaamaan oikeaa levyä. MEDIA_ROOT muodostuu
   `<mount>/private-photos`-hakemistoksi. Sovellus tarkistaa todellisen mountin ennen
   tallentamista. Ilman pysyvää mountia kuva hylätään lomakkeella; saalis ilman kuvaa
   ja sovelluksen muut toiminnot toimivat normaalisti.
3. Varmista webpalvelun prosessin kirjoitus- ja lukuoikeus Volumeen. Älä käytä
   erillisten levyjen replikoita: kaikkien kuvapyyntöjen pitää saavuttaa sama levy.
4. Ota käyttöön Volumen varmuuskopiot ja varmistu palautuksesta yhdessä PostgreSQL:n
   varmuuskopioiden kanssa. Paikalliset vanhat kuvat eivät siirry Gitiin tai
   tuotantoon automaattisesti.
5. Nykyinen Railway pre-deploy ajaa migraation `0013_catch_photo`. Se lisää vain
   tyhjän valinnaisen kentän eikä käsittele kuvatiedostoja. Volumea ei tarvita build-
   tai pre-deploy-vaiheessa. Tarkista deployn jälkeen omalla käyttäjällä kuvan
   tallennus, luku ja säilyminen uudelleenkäynnistyksen yli.

Railwayn aktiivisia palveluasetuksia ei ole tarkastettu tai muutettu tämän työn
kuluessa. Koodin Railway-konfiguraatio ei määritä kuville pysyvää levyä.
Ohjeet: https://docs.railway.com/volumes ja https://docs.railway.com/volumes/backups

TOP 3 sisältää vain kirjautuneen käyttäjän nykyisen Suomen kalenterikuukauden
reissuille kirjatut saaliit, joilla on paino. Järjestys: paino laskevasti, ID
nousevasti. Ennätykset ovat omista saaliista (positiivinen paino/pituus), samalla
ID-tasatilannesäännöllä. Kortit eivät näytä kalapaikkaa eikä GPS-tietoja. Kuvassa
itsessään näkyviä maisemia ei automaattisesti anonymisoida, mutta kuvat ovat yksityisiä.

### Tämän ominaisuuden tiedostot

- Malli ja migraatio: `fishinglog/models.py`, `fishinglog/migrations/0013_catch_photo.py`.
- Kuvat ja niiden elinkaari: `fishinglog/photos.py`, `fishinglog/photo_views.py`,
  `fishinglog/photo_signals.py`, `fishinglog/apps.py`.
- Lomakkeet, reitit ja näkymät: `fishinglog/forms.py`, `fishinglog/views.py`,
  `fishinglog/urls.py`, `fishinglog/admin.py`.
- TOP 3 ja ennätykset: `fishinglog/records.py`, `fishinglog/statistics.py`.
- Templatet hakemistossa `fishinglog/templates/fishinglog/`: `catch_formset.html`,
  `form.html`, `trip_detail.html`, `home.html`, `statistics.html`,
  `fish_record_card.html`, `monthly_top.html`.
- Asetukset ja riippuvuudet: `fishing_ai/settings.py`, `requirements.txt`,
  `.env.example`, `.gitignore`.
- Testit: `fishinglog/test_photos_records.py`.
- Ohjeet: `README.md`.

### Kalastusavustajan julkinen paikkahaku

Omat FishingSpotit ohittavat julkisen geokoodauksen. Julkiselle paikannimelle kokeillaan
ensin nykyistä FMI-paikkahakua, sitten tarvittaessa OpenStreetMap Nominatimia.
Koko kysymystä, omien kalapaikkojen nimiä/koordinaatteja tai muistiinpanoja ei lähetetä
Nominatimille. Haku tapahtuu vain avustajan lomakkeen lähetyksestä, ei kirjoittaessa.

Nominatimin [käyttöehdot](https://operations.osmfoundation.org/policies/nominatim/)
rajaavat koko sovelluksen yhteen pyyntöön sekunnissa. Tietokannan yhteinen pyyntöportti
estää rinnakkaiset haut myös Railwayn eri workereilta; varattu palvelu epäonnistuu
hallitusti. Julkiset tulokset välimuistitetaan 24 tunniksi, tyhjät/epäselvät tunniksi.
Palvelu soveltuu kohtuulliseen käyttäjämäärään eikä takaa saatavuutta. Nominatim-palvelun
osoitteen voi vaihtaa ympäristömuuttujalla `NOMINATIM_URL` ilman koodimuutosta.
Paikkahaun lähdemerkintä näytetään vastauksessa. API-avainta ei tarvita.

Julkinen sääpaikka ja ajanjakso säilyvät käyttäjän istunnossa enintään kuusi tuntia.
Vain selvä jatkokysymys voi käyttää edellistä aluetta varapaikkana, ja siitä näytetään
ilmoitus. Alueellisesti rajattu haku hyväksyy vain nimeltään sopivan, yksiselitteisen
suomalaisen tuloksen enintään 100 km:n päästä alueen edustavasta pisteestä. Tämä on
alueellinen tarkistus, ei järven rantaviivan tunnistus; epäselvät paikat hylätään.

Ennen käyttöä aja `python manage.py migrate` (migraatio 0014 lisää jaetun julkisen
paikkavälimuistin ja pyyntöportin). Railwayn tavallinen migraatiovaihe hoitaa tämän.

Paikkatunnistus ei käytä järvien nimilistaa. Se poimii myös pienellä kirjoitetun
paikkaehdokkaan, muodostaa enintään kolme perusmuotoehdokasta ja tarkistaa
hakutuloksen nimen suhteessa alkuperäiseen taivutusmuotoon. Pitkä e-vartalo ja
vokaalin kahdentava illatiivi huomioidaan yleisillä säännöillä. Ristiriitaiset
vahvistetut tulokset hylätään; tavalliset kysymys-, sää- ja kalastussanat suodatetaan.
Tämä ei ole täydellinen suomen taivutusmoottori: epäselvään nimeen pyydetään tarkennus.
Koko julkisen paikan ratkaisulle on 20 sekunnin aloitusbudjetti; jo aloitettu pyyntö
voi kestää oman aikakatkaisunsa loppuun. Budjetin loppuessa keskeneräistä ehdokasvertailua
ei hyväksytä. FMI:n ja Nominatimin olemassa olevat pyyntökohtaiset timeoutit säilyvät.
