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
Omistajan poistaminen on estetty niin kauan kuin hänellä on reissuja.
