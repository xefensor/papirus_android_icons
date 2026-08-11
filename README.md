<p align="center">
  <img src="preview.png" alt="Papirus Android preview"/>
</p>

# Papirus Icon Pack for Android

Papirus for Android is a maintained community fork of the original Papirus Android icon pack. It keeps Android-specific artwork where it already exists and reuses actively maintained desktop Papirus artwork when the app identity can be verified safely.

This fork is maintained at `xefensor/papirus_android_icons`. The original Papirus project and its contributors remain credited; this repository does not claim authorship of inherited artwork.

## Features

- Fully open source
- More than 2300 mapped icons
- Android-specific Papirus artwork preserved
- Verified desktop Papirus artwork sync
- Arcticons and Lawnicons component-mapping assistance with false-positive protection
- Real APK builds that generate and package all launcher PNG resources
- Lawnchair, Nova and many other icon-pack compatible launchers
- Included Papirus wallpapers

## Install

Releases are published through the repository's GitHub Releases page:

`https://github.com/xefensor/papirus_android_icons/releases`

Development/test APKs are also produced by GitHub Actions for pull requests. Debug builds use a separate `.test` application ID so they can coexist with the normal maintained package.

## Icon requests

The abandoned email-based icon request endpoint is intentionally disabled because it pointed to a previous maintainer's personal address. Missing apps can still be identified with CandyBar's missing-icon report and audited with the maintenance tooling in this repository.

`scripts/audit_icon_request.py` accepts the plain-text CandyBar Icon Request report and separates already-covered components, stale launcher activities, external icon-pack identities and genuinely missing artwork.

## Maintenance

Android-specific artwork in `src/` has priority over desktop artwork. Existing Android icons are never overwritten merely because a similarly named icon exists in desktop Papirus.

### Desktop artwork sync

`scripts/sync_desktop_icons.py` imports missing application artwork from `PapirusDevelopmentTeam/papirus-icon-theme`. Imported files are recorded in `desktop-sync.json`, allowing later upstream updates without taking ownership of manually maintained Android artwork.

```bash
git clone https://github.com/PapirusDevelopmentTeam/papirus-icon-theme.git ../papirus-icon-theme
python3 scripts/sync_desktop_icons.py ../papirus-icon-theme --dry-run
python3 scripts/sync_desktop_icons.py ../papirus-icon-theme \
  --upstream-ref "$(git -C ../papirus-icon-theme rev-parse HEAD)"
```

### Android-relevant artwork sync

`scripts/sync_android_artwork.py` discovers brand-new Android-relevant icons from desktop Papirus. It combines desktop artwork with Arcticons and Lawnicons mappings and auto-imports only candidates with strong identity evidence.

Candidates that cannot be proven safely are reported as `REVIEW` rather than guessed.

```bash
git clone https://github.com/PapirusDevelopmentTeam/papirus-icon-theme.git ../papirus-icon-theme
python3 scripts/sync_android_artwork.py ../papirus-icon-theme --list
```

To apply automatic candidates:

```bash
python3 scripts/sync_android_artwork.py ../papirus-icon-theme \
  --write \
  --upstream-ref "$(git -C ../papirus-icon-theme rev-parse HEAD)"
DB_FILE=./data.json APPFILTER_FILE=./app/src/main/assets/appfilter.xml \
  python3 scripts/generate_appfilter.py
```

Imported desktop artwork is recorded in `desktop-sync.json`. Imported mappings are recorded in `external-mappings.json` and are excluded from future inference anchors.

### Android component mapping sync

`data.json` is the authoritative Papirus component database. `scripts/sync_external_mappings.py` can learn additional package/activity variants from Arcticons and Lawnicons without fuzzy app-name matching.

Mappings imported from external packs, and mappings verified manually on devices, are provenance-tracked and excluded from later inference. This prevents one accepted mapping from recursively teaching the importer unrelated mappings.

```bash
python3 scripts/sync_external_mappings.py
python3 scripts/sync_external_mappings.py --source arcticons
python3 scripts/sync_external_mappings.py --source lawnicons
```

## Building

Launcher icons are generated resources. Running Gradle alone is not enough to build a complete icon-pack APK.

```bash
make VALIDATE=false build
./gradlew assembleRelease
```

`VALIDATE=false` is currently required because the inherited source tree intentionally includes a small number of manually selectable icons without Android component mappings.

CI performs the same resource generation, verifies every source SVG has a generated PNG, checks mapping/appfilter consistency, then builds both release and installable debug APK artifacts.

## Upstream and attribution

Papirus Android is based on the original work from the Papirus Development Team and its contributors. Desktop artwork is synchronized from:

`https://github.com/PapirusDevelopmentTeam/papirus-icon-theme`

Inherited code, artwork and contributor attribution remain governed by their respective repository licenses and history.
