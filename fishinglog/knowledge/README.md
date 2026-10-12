# Kalastustietopohjan runko

Tässä hakemistossa ei vielä ole kalastusohjeita tai hyväksyttyjä lähteitä.
`species/*.json` ja `conditions.json` sisältävät tyhjät `rules`-listat.
`sources.json` sisältää tyhjän lähdeluettelon. Testien synteettiset sääntö- ja
lähdefixturet eivät kuulu tähän tietopohjaan.

## Tiedostot ja tarkistus

- `catalog.json`: hallitut tunnisteet, kentät, mittayksiköt ja tekniset arvorajat.
- `schema.json`: JSON Schema Draft 2020-12; koko nipun rakenteet `$defs`-osassa.
- `sources.json`: lähdekohtainen id, otsikko, julkaisija, HTTPS-osoite,
  tarkistuspäivä, tiedon luonne, soveltuvuus ja tarkka kohta lähteessä.
- `species/<laji>.json`: kyseisen lajin säännöt.
- `conditions.json`: useita lajeja koskevat yhteiset säännöt.

Aja projektin juuresta `python manage.py check_fishing_knowledge`.
Validaattori toimii ilman verkkopyyntöjä. Schema tarkistaa rakenteen ja kenttätyypit;
Python-validaattori tarkistaa katalogiin kuuluvuuden, tiedostojen väliset viitteet,
id:iden yksilöllisyyden, mittayksikön yhteensopivuuden sekä min <= max -ehdon.
Kaikki sääntötiedostot validoidaan myös draft-tilassa. Virhe estää aktiivisten sääntöjen
lataamisen; viallisia sääntöjä ei ohiteta hiljaisesti. Uusi laji lisätään katalogiin ja
omaksi tiedostokseen, eikä schemaan tarvitse kopioida lajiluetteloa.

## Säännön sopimus

Kaikki kentät ovat pakollisia:
`id`, `version`, `status`, `species`, `when`, `requires`, `recommend`, `reason_fi`,
`evidence_type`, `source_ids`, `unknown_policy`, `conflict_group`.

- `id` on yksilöllinen koko nipussa. Uusi versio korvaa saman säännön; historia on Gitissä.
- `version` on positiivinen kokonaisluku; `status`: draft / approved / retired.
- `species` luettelee soveltuvat lajit. Lajitiedostossa vain tiedoston oma laji.
- `when` yhdistää kenttien ehdot JA-operaatiolla; luettelon tunnisteet ovat vaihtoehtoja.
  Numeerinen ehto on `{ "min": ..., "max": ..., "unit": ... }`, molemmat rajat mukana.
- `requires` nimeää soveltamisessa tunnetuiksi vaaditut kentät.
- `recommend` sisältää vain katalogin suosituskenttiä. Mittavälit eivät ole mitattuja havaintoja.
- `reason_fi` on lähteeseen perustuva lyhyt perustelu, ei prompttiohje.
- `source_ids` voi draftissa olla tyhjä; kaikki annetut id:t on silti löydyttävä lähdeluettelosta.
- `unknown_policy`: skip / conditional_only. Tulevan valitsijan tulee joko jättää sääntö
  käyttämättä puuttuvan tiedon takia tai näyttää se selvästi ehdollisena vaihtoehtona.
- `conflict_group` ryhmittelee keskenään vertailtavat suositukset; tämä runko ei ratkaise ristiriitoja.

`active_rules()` palauttaa vain validoidut approved-säännöt, joilla on olemassa olevat
lähdeviitteet. Se ei vielä arvioi olosuhteiden soveltuvuutta eikä anna suosituksia.
Tietopohjaa ei ole yhdistetty Kalastusavustajaan. Hyväksyntä ja lähteen sisällön tarkistus
ovat ylläpitäjän tehtäviä: validointi ei todista lähteen väitettä oikeaksi eikä avaa URL:ia.

## Tuntemattomat tiedot ja yksiköt

Ainoa tuntemattoman arvon esitysmuoto on JSON `null`, ei nolla, tyhjä merkkijono tai
keksitty keskiarvo. Stringiä `unknown` ei käytetä katalogitunnisteena.
`when`-ehdon null ilmaisee nimenomaisesti tuntemattoman kentän; samaa kenttää ei voi
samalla vaatia tunnetuksi `requires`-listassa. Puuttuva `when`-kenttä ei aseta ehtoa.
Validaattori ei päättele tai täytä havaintoja eikä muunna yksiköitä.

- `bottom_depth`: pohjan syvyys (m).
- `fishing_depth`: kalastussyvyys (m).
- `fish_holding_depth`: erikseen ilmoitettu/havaittu kalan oleskelusyvyys (m), ei suosituskenttä.
- `lure_running_depth`: vieheen uintisyvyys (m).
- Vieheen pituus: cm. Veden ja ilman lämpötila: erilliset degC-kentät.
- Tuuli: m/s; sade: mm/h; ilmanpaine: hPa; painetrendin muutosnopeus: hPa/h.
- Pilvisyys: percent 0–100; paikallinen kellonaika: hour 0–24.

Arvorajat ovat teknisiä rajoja, eivät kalojen käyttäytymistä koskevia ohjeita.
Yön yli ulottuva kellonaikaväli kuvataan myöhemmin erillisinä ehtoina; min > max ei käy.
`normal`-vedenkirkkaus on käyttäjän suhteellinen havainto, ei säästä päätelty mittaus.
Väriryhmien nimet eivät vielä sisällä väitteitä niiden tehokkuudesta.

## Sisältötyön seuraava vaihe

Hanki lajikohtaiset, Suomen järvikalastukseen soveltuvat lähteet käyttäytymisestä,
vuodenajasta ja veden lämpötilasta; menetelmien ja vieheiden soveltuvuudesta;
perustelluista koko- ja uintisyvyysväleistä; veden kirkkauden ja valoisuuden yhteydestä
värin valintaan. Merkitse tarkka tukikohta, alueellinen rajaus ja tiedon luonne.
Erota tutkimustulos asiantuntijaohjeesta ja käytännön kokeiluvinkistä. Ilmanpaineen,
painetrendin, sateen ja tuulen vaikutuksista tarvitaan erikseen tarkistettu näyttö;
puuttuvaa näyttöä ei korvata yleisellä varmana esitetyllä säännöllä.
