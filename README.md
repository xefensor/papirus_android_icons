<p align="center">
  <img src="https://raw.githubusercontent.com/PapirusDevelopmentTeam/papirus_icons/master/preview.png" alt="preview"/>
</p>

# Papirus Icon Pack
Popular Linux icon theme now on Android!

This repository is a maintained community fork of the Papirus Android icon pack. The goal is to keep the Android pack current while continuing to reuse the actively maintained desktop Papirus artwork where it makes sense.

# Supported Launchers
Below launchers have been tested to be working successfully with Papirus Icon among others. Feel free to add yours:

- Flick
- Holo
- Lawnchair
- Lucid
- Nova
- Posidon
- Smart
- HiOS
- _and many others..._

# Features
- Fully Open Source
- Pixel perfect
- More than 2300 mapped icons
- Inspired by Material design
- Icon Request option
- Check Update function
- 8 Cloud Wallpapers

# Maintenance

Android-specific artwork in `src/` has priority over desktop artwork. Existing Android icons are therefore never overwritten merely because a similarly named icon exists in the desktop Papirus theme.

## Desktop artwork sync

The repository includes `scripts/sync_desktop_icons.py` for importing missing application artwork from `PapirusDevelopmentTeam/papirus-icon-theme`. Files imported by the script are recorded in `desktop-sync.json`, allowing later upstream updates to those imported files without taking ownership of manually maintained Android artwork.

Example:

```bash
git clone https://github.com/PapirusDevelopmentTeam/papirus-icon-theme.git ../papirus-icon-theme
python3 scripts/sync_desktop_icons.py ../papirus-icon-theme --dry-run
python3 scripts/sync_desktop_icons.py ../papirus-icon-theme \
  --upstream-ref "$(git -C ../papirus-icon-theme rev-parse HEAD)"
```

Desktop aliases/symlinks are currently skipped rather than duplicated. Normalized filename collisions are reported and must be reviewed manually.

## Android-relevant artwork sync

`scripts/sync_android_artwork.py` is the safer way to discover **brand-new** Android icons from the desktop theme. It combines the desktop Papirus application artwork with live Arcticons and Lawnicons mappings and only auto-imports candidates with strong identity evidence.

A new icon must:

- have an exact normalized drawable-name match between a canonical desktop Papirus SVG and an Android icon-pack drawable,
- not replace an existing Android SVG or Papirus drawable,
- not reuse an Android component that Papirus already maps elsewhere,
- have the desktop/app identity represented in the Android package name itself, and
- pass the limits and explicit collision exclusions in `artwork-sync-policy.json`.

Activity names are intentionally not treated as identity evidence. This avoids false matches from generic frameworks or same-name desktop and Android applications. Candidates that cannot be proven safely are printed as `REVIEW` and are left for manual inspection or the in-app Icon Request flow.

Audit current desktop Papirus against the Android pack:

```bash
git clone https://github.com/PapirusDevelopmentTeam/papirus-icon-theme.git ../papirus-icon-theme
python3 scripts/sync_android_artwork.py ../papirus-icon-theme --list
```

Import only automatically verified candidates and record the exact desktop upstream revision:

```bash
python3 scripts/sync_android_artwork.py ../papirus-icon-theme \
  --write \
  --upstream-ref "$(git -C ../papirus-icon-theme rev-parse HEAD)"
DB_FILE=./data.json APPFILTER_FILE=./app/src/main/assets/appfilter.xml \
  python3 scripts/generate_appfilter.py
```

Imported desktop artwork is recorded in `desktop-sync.json`. Its generated Android mappings are also recorded in `external-mappings.json`, so they never become self-reinforcing evidence for later automatic matching.

## Android component mapping sync

Artwork synchronization and Android app/component mapping are intentionally separate jobs. `data.json` remains the authoritative Papirus mapping database.

`scripts/sync_external_mappings.py` can learn additional package/activity variants from actively maintained Android icon projects. The built-in sources are Arcticons and Lawnicons.

The mapping sync deliberately does **not** fuzzy-match app names. An external drawable group is accepted only when it already points to exactly one Papirus icon and has strong evidence for that relationship:

- its normalized drawable name matches the Papirus drawable name, or
- at least two existing trusted Android components independently link the external group to the same Papirus icon.

Groups that point to multiple Papirus icons, weak single-component matches, and new components for which different sources disagree are skipped rather than guessed.

Mappings imported from external packs are recorded in `external-mappings.json`. They are never reused as evidence on later synchronization runs, preventing imported mappings from recursively teaching the importer more mappings.

Dry-run both built-in sources:

```bash
python3 scripts/sync_external_mappings.py
```

Inspect one source:

```bash
python3 scripts/sync_external_mappings.py --source arcticons
python3 scripts/sync_external_mappings.py --source lawnicons
```

Apply trusted inferred mappings and regenerate the tracked appfilter:

```bash
python3 scripts/sync_external_mappings.py --write
DB_FILE=./data.json APPFILTER_FILE=./app/src/main/assets/appfilter.xml \
  python3 scripts/generate_appfilter.py
make test
```

## Building

The launcher icons are generated resources; running Gradle alone is not enough to create a complete icon-pack APK. Generate the 192 px PNG resources and XML files before assembling Android:

```bash
make VALIDATE=false build
./gradlew assembleRelease
```

`VALIDATE=false` is currently required because the inherited source tree intentionally contains a small number of manually selectable icons without Android component mappings.

CI performs the same real-resource build, checks that every source SVG generated a launcher PNG, validates mapping/appfilter consistency, and then builds and uploads the release APK artifact. The existing in-app Icon Request feature remains the fallback for applications that cannot be resolved safely from upstream mappings.

# Install
You can [download icon pack](https://www.pling.com/p/1662847/) directly from the Android browser or download on PC and send to phone via KDE Connect/Send Anywhere/Android File Transfer or adb.
Application have "Check Update" button for features updates.

# Priority icon requests
1. If you donate
2. Popular applications
3. Open source applications
4. Games
