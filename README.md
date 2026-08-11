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
- More than 1500 icons
- Inspired by Material design
- Icon Request option
- Check Update function
- 8 Cloud Wallpapers

# Maintenance

Android-specific artwork in `src/` has priority over desktop artwork. Existing Android icons are therefore never overwritten merely because a similarly named icon exists in the desktop Papirus theme.

The repository includes `scripts/sync_desktop_icons.py` for importing missing application artwork from `PapirusDevelopmentTeam/papirus-icon-theme`. Files imported by the script are recorded in `desktop-sync.json`, allowing later upstream updates to those imported files without taking ownership of manually maintained Android artwork.

Example:

```bash
git clone https://github.com/PapirusDevelopmentTeam/papirus-icon-theme.git ../papirus-icon-theme
python3 scripts/sync_desktop_icons.py ../papirus-icon-theme --dry-run
python3 scripts/sync_desktop_icons.py ../papirus-icon-theme \
  --upstream-ref "$(git -C ../papirus-icon-theme rev-parse HEAD)"
```

Desktop aliases/symlinks are currently skipped rather than duplicated. Normalized filename collisions are reported and must be reviewed manually.

Artwork synchronization and Android app/component mapping are intentionally separate jobs: the desktop theme supplies Papirus artwork, while `data.json` remains the source for Android package/activity mappings. This lets us later import mappings from maintained Android icon projects without coupling them to artwork synchronization.

# Install
You can [download icon pack](https://www.pling.com/p/1662847/) directly from the Android browser or download on PC and send to phone via KDE Connect/Send Anywhere/Android File Transfer or adb.
Application have "Check Update" button for features updates.

# Priority icon requests
1. If you donate
2. Popular applications
3. Open source applications
4. Games
