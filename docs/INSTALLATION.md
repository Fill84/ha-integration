# Installeren en bijwerken

Deze integratie bestaat uit twee **afzonderlijke** onderdelen: de Home Assistant-integratie in `Fill84/ha-integration` en de desktopapp in `Fill84/HA-Companion-App`. Installeer of werk eerst de HA-integratie bij, herstart HA volledig en installeer of werk daarna de desktopapp bij. Een desktoprelease met een integratie-zip in zijn eigen release werkt HACS niet automatisch bij; HACS leest de afzonderlijke integratierepository.

## Home Assistant via HACS

1. Maak een back-up van je HA-configuratie. Bestaande apparaat- en entity-ID's moeten bij de upgrade behouden blijven.
2. Voeg `https://github.com/Fill84/ha-integration` in HACS toe als **Integration** onder *Custom repositories*. Staat de repository er al, open dan de bestaande HACS-installatie.
3. Kies de nieuwste **gepubliceerde, stabiele** versie en laat HACS de integratie downloaden. Een lokale commit of manifestversie die nog niet naar deze repository is gepusht, verschijnt niet als update.
4. Herstart Home Assistant volledig. Voeg daarna onder *Instellingen → Apparaten en diensten → Integratie toevoegen* eenmaal **Desktop App** toe als hub, als deze nog niet bestaat. Verwijder bestaande apparaatentries niet om een update af te dwingen.
5. Controleer in een browser `https://<jouw-ha-host>/api/desktop_app/ping`. Een HTTP 200-antwoord bevestigt dat de integratie-API geladen is; het bewijst nog geen werkende desktopregistratie.

Handmatige installatie: kopieer uitsluitend `custom_components/desktop_app/` uit een gecontroleerde integratierelease naar `<config>/custom_components/desktop_app/`, en voer daarna stap 4–5 uit. Meng geen losse bestanden uit verschillende versies.

## Desktopapp op Windows

1. Download de Windows **NSIS-installer** van de bijbehorende, gepubliceerde desktoprelease. Een lokaal `target/`-bestand of een oude 1.0.4-installer is geen nieuwe release. Controleer de versie en de SHA-256 tegen het release-manifest. Een publiek installatiebestand moet door de releasepoort zijn gegaan.
2. Start de installer met administratorrechten; het installatiedoel is per machine. De installer kan de Microsoft WebView2-bootstrapper downloaden als WebView2 ontbreekt, dus daarvoor is internet nodig.
3. Kies de optionele CPU-temperatuurprovider alleen als je die meting wilt. De keuze installeert de meegeleverde, officieel ondertekende PawnIO-driver en onze eigen beperkte Rust-sensorservice; er is geen afzonderlijke PawnIO-app of .NET-helper nodig. Zonder deze keuze blijven basismetingen beschikbaar en is CPU-temperatuur `unknown`.
4. Start de app als normale gebruiker. Vul de basis-URL van HA zonder `/api` en een persoonlijk *Long-Lived Access Token* in. De app bewaart het token in de OS-kluis en registreert het apparaat via de geauthenticeerde HA-API. Bewaar of deel het token niet in screenshots of logs.
5. Schakel in de app-instellingen de CPU-temperatuurprovider ook in als je hem tijdens installatie koos. Controleer in HA de Online-entity en bijvoorbeeld CPU-gebruik, uptime en, op ondersteunde hardware, CPU-temperatuur. `unknown` betekent dat er geen bevestigde meting is.

Bij een upgrade blijven de configuratie, het bestaande apparaat en de entity-ID's behouden. De installer verwijdert bij uninstall de eigen sensorservice, maar verwijdert een mogelijk gedeelde PawnIO-driver niet blind. Verwijder een oud HA-apparaat niet als herstelpoging; gebruik **Reconnect** in de app als de registratie ontbreekt. Een gewijzigde server of token vraagt een nieuwe registratie.

## Andere desktopplatformen

Linux en macOS lezen beschikbare OS-/hardwarebronnen zonder Windows-driver. De code bevat deze paden, maar deze releasekandidaat heeft nog geen fysieke macOS-/Linux-installatieproef. Gebruik pas een als ondersteund gepubliceerde build nadat de platformproeven zijn vastgelegd. Niet alle hardware publiceert alle sensoren.

## Uptime en beschikbaarheid

`system_uptime` blijft een numerieke duur in seconden voor automatiseringen en statistieken. De state heeft daarnaast `human_readable` voor een leesbare dashboardrij. Gebruik in een standaard Home Assistant Entities-kaart een `attribute`-rij met `entity: sensor.<apparaat>_system_uptime` en `attribute: human_readable`; de sensor-ID verandert daarbij niet. De status van een offline apparaat is **unavailable** voor gewone meetsensoren; de Online-binaire sensor toont zelf **offline**.

## Herstel en rollback

- **Ping 404:** controleer of de hub-integratie geladen is, of HA volledig is herstart, en of de URL van HA klopt.
- **Registratie 401/403:** controleer het persoonlijke token en, bij een bestaand apparaat, de eigenaar van de HA-registratie. Een andere gewone HA-gebruiker mag de bestaande webhook niet overnemen.
- **Online, maar geen temperatuur:** controleer eerst de optionele installerkeuze, de app-instelling en de providerstatus-attributen. Een unsupported CPU krijgt geen geschatte temperatuur.
- **HACS biedt geen nieuwe versie:** controleer of er daadwerkelijk een hogere, gepubliceerde versie in `Fill84/ha-integration` bestaat. De desktoprelease alleen is onvoldoende.
- **Rollback:** herstel de HA-configuratieback-up en installeer de vorige integratie- en desktopversies als paar. Verwijder of hernoem bestaande entities niet tijdens herstel. Controleer na herstart zowel de Online-entity als enkele bestaande entity-ID's.

Een release is pas geschikt voor algemeen gebruik na de tests in de [verificatiestatus van de desktoprepository](https://github.com/Fill84/HA-Companion-App/blob/main/docs/plans/2026-09-24-verificatiestatus.md).
