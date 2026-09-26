# Installeren en bijwerken

Deze integratie bestaat uit twee **afzonderlijke** onderdelen: de Home Assistant-integratie in `Fill84/ha-integration` en de desktopapp in `Fill84/HA-Companion-App`. Installeer of werk eerst de HA-integratie bij, herstart HA volledig en installeer of werk daarna de desktopapp bij. Een desktoprelease met een integratie-zip in zijn eigen release werkt HACS niet automatisch bij; HACS leest de afzonderlijke integratierepository.

## Home Assistant via HACS

1. Maak een back-up van je HA-configuratie. Bestaande apparaat- en entity-ID's moeten bij de upgrade behouden blijven.
2. Voeg `https://github.com/Fill84/ha-integration` in HACS toe als **Integration** onder *Custom repositories*. Staat de repository er al, open dan de bestaande HACS-installatie.
3. Kies de nieuwste **gepubliceerde, stabiele** versie en laat HACS de integratie downloaden. Een lokale commit of manifestversie die nog niet naar deze repository is gepusht, verschijnt niet als update.
4. Herstart Home Assistant volledig zodat de nieuwe custom integration beschikbaar is. Met integratie 1.0.12 en desktopapp 1.0.6 hoef je geen lege **Desktop App**-hub meer toe te voegen: open de desktopapp en verbind deze met HA. Voor de **eerste** computer is een HA-beheerderstoken nodig, omdat HA alleen beheerders een config entry laat maken. De desktop maakt zijn eigen apparaat-entry en webhook aan. Volgende computers kunnen zich op dezelfde manier aanmelden. De oudere integratie 1.0.11 werkt nog volgens de oude hubstap.
5. Controleer onder *Instellingen → Apparaten en diensten → Desktop App* of uitsluitend echte computers staan en de sensoren verse waarden ontvangen. `/api/desktop_app/ping` kan na de eerste aanmelding pas na een HA-herstart beschikbaar zijn; de app gebruikt tot die tijd de ingebouwde HA-webhookroute. HTTP 200 op die ping is geen bewijs voor sensorupdates.

Handmatige installatie: kopieer uitsluitend `custom_components/desktop_app/` uit een gecontroleerde integratierelease naar `<config>/custom_components/desktop_app/`, en voer daarna stap 4–5 uit. Meng geen losse bestanden uit verschillende versies.

## Desktopapp op Windows

1. Download de Windows **NSIS-installer** van de bijbehorende, gepubliceerde desktoprelease. Een lokaal `target/`-bestand of een oude 1.0.4-installer is geen nieuwe release. Controleer de versie en de SHA-256 tegen het release-manifest. Een publiek installatiebestand moet door de releasepoort zijn gegaan.
   Versie 1.0.5 is [hier gepubliceerd](https://github.com/Fill84/HA-Companion-App/releases/tag/1.0.5) voor Windows x64. De app en installer zijn ongetekend; Windows kan **Onbekende uitgever** of een SmartScreen-waarschuwing tonen. De meegeleverde PawnIO-driver heeft een eigen leveranciershandtekening. Controleer de SHA-256 op de releasepagina voordat je de installer uitvoert.
2. Start de installer met administratorrechten; het installatiedoel is per machine. De installer kan de Microsoft WebView2-bootstrapper downloaden als WebView2 ontbreekt, dus daarvoor is internet nodig.
3. De installer installeert standaard de meegeleverde, ondertekende PawnIO-driver en de eigen Rust-sensorservice als onderdeel van de Windows-app. Er is geen aparte sensorapp, .NET-helper of tweede keuze in de app-instellingen nodig. Een niet-ondersteunde CPU of ontbrekende driver levert `unknown` op in plaats van een geschatte temperatuur.
4. Start de app als normale gebruiker. Vul de basis-URL van HA zonder `/api` en een persoonlijk *Long-Lived Access Token* in. De app bewaart het token in de OS-kluis en registreert het apparaat via de geauthenticeerde HA-API. Bewaar of deel het token niet in screenshots of logs.
5. Controleer in HA de Online-entity en bijvoorbeeld CPU-gebruik, uptime en, op ondersteunde hardware, CPU-temperatuur. `unknown` betekent dat er geen bevestigde meting is. Op Windows kun je bij een ontbrekende CPU-temperatuur controleren of de services `HaCompanionSensors` en `PawnIO` draaien.

Bij een upgrade blijven de configuratie, het bestaande apparaat en de entity-ID's behouden. De installer verwijdert bij uninstall de eigen sensorservice, maar verwijdert een mogelijk gedeelde PawnIO-driver niet blind. Verwijder een oud HA-apparaat niet als herstelpoging; gebruik **Reconnect** in de app als de registratie ontbreekt. Een gewijzigde server of token vraagt een nieuwe registratie.

## Andere desktopplatformen

Linux en macOS lezen beschikbare OS-/hardwarebronnen zonder Windows-driver. Versie 1.0.5 bevat een macOS Apple Silicon-DMG en Linux x86_64-pakketten. Deze zijn gebouwd en automatisch getest, maar een interactieve installatie en sensor-naar-HA-proef ontbreekt nog; ze hebben daarom nog geen gelijkwaardige runtimevalidatie als Windows. Intel-Mac- en Linux-ARM64-installers zijn niet meegeleverd. Niet alle hardware publiceert alle sensoren.

## Uptime en beschikbaarheid

`system_uptime` blijft een numerieke duur in seconden voor automatiseringen en statistieken. De state heeft daarnaast `human_readable` voor een leesbare dashboardrij. Gebruik in een standaard Home Assistant Entities-kaart een `attribute`-rij met `entity: sensor.<apparaat>_system_uptime` en `attribute: human_readable`; de sensor-ID verandert daarbij niet. De status van een offline apparaat is **unavailable** voor gewone meetsensoren; de Online-binaire sensor toont zelf **offline**.

## Herstel en rollback

- **Ping 404:** vóór de eerste aanmelding en totdat HA na die aanmelding herstart is, kan de compatibiliteits-API ontbreken. De nieuwe desktop gebruikt dan HA's ingebouwde config-flow- en webhook-API. Controleer of de integratie via HACS geïnstalleerd is, HA na installatie herstart is en de basis-URL klopt.
- **Registratie 401/403:** controleer het persoonlijke token en, bij een bestaand apparaat, de eigenaar van de HA-registratie. Een andere gewone HA-gebruiker mag de bestaande webhook niet overnemen. Een oude registratie zonder eigenaar moet één keer met een HA-beheerderstoken aan een eigenaar worden gekoppeld; behoud daarbij de bestaande device-ID en webhook.
- **Online, maar geen temperatuur:** controleer de Windows-sensordiensten en de `provider_status`- en `measurement_source`-attributen. Een niet-ondersteunde CPU krijgt geen geschatte temperatuur.
- **HACS biedt geen nieuwe versie:** controleer of er daadwerkelijk een hogere, gepubliceerde versie in `Fill84/ha-integration` bestaat. De desktoprelease alleen is onvoldoende.
- **Rollback:** herstel de HA-configuratieback-up en installeer de vorige integratie- en desktopversies als paar. Verwijder of hernoem bestaande entities niet tijdens herstel. Controleer na herstart zowel de Online-entity als enkele bestaande entity-ID's.

Een release is pas geschikt voor algemeen gebruik na de tests in de [verificatiestatus van de desktoprepository](https://github.com/Fill84/HA-Companion-App/blob/main/docs/plans/2026-09-24-verificatiestatus.md).
