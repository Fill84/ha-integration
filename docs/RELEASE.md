# HACS-releaseprocedure

De Home Assistant-integratie heeft een **eigen** repository en eigen versie. Een release of zip in de desktoprepository verschijnt niet als HACS-update. HACS moet `custom_components/desktop_app/manifest.json`, `hacs.json` en een publieke integratierelease uit `Fill84/ha-integration` kunnen ophalen.

Voorbereiding van 1.0.11:

1. Controleer dat manifest `version` exact `1.0.11` vermeldt, `custom_components/desktop_app/` in de repository-root staat en `hacs.json` geldig JSON is.
2. Voer `python -m pytest -q` uit en valideer alle JSON-bestanden en Python-syntax. Test een upgrade op een echte Home Assistant-installatie, inclusief behoud van bestaande entity-ID's, statische en dynamische sensoren, offline/online, config-entry reload en meerdere apparaten. Test ook de geclaimde minimumversie 2026.9.0.
3. Controleer de desktopversie waarmee deze integratie wordt uitgebracht en leg beide commit-SHA's vast. Test Windows op `phill-pc` en `beast-unit`; documenteer eventuele nog niet uitgevoerde Linux/macOS-proeven als releasebeperking.
4. Commit de integratierepository afzonderlijk, zonder niet-gerelateerde lokale wijzigingen. Pas na de afgesproken releasepoort: push de commit, maak een *nieuwe* tag/release `1.0.11` in **de integratierepository**, en controleer dat HACS versie 1.0.11 als update aanbiedt. Gebruik geen bestaande tag opnieuw.
5. Installeer via HACS bovenop een bestaande 1.0.10-installatie, herstart HA en controleer de bestaande entity-ID's en automatiseringen. Publiceer de desktoprelease pas met de geteste integratiecommit.

De volgorde, installatiekeuzes en rollback voor gebruikers staan in [INSTALLATION.md](INSTALLATION.md). Dit document autoriseert geen voortijdige push of release.
