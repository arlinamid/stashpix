# Packaging

Build a standalone, Python-free bundle and a Windows MSI installer.

## Output

```
dist/stashpix/
  ├── stashpix.exe        # CLI  (stashpix embed / extract / extract-geo / verify-visible / serve / gui)
  ├── stashpix-gui.exe    # desktop GUI
  └── _internal/       # bundled Python runtime, deps and data (api/static, ...)

packaging/out/stashpix-<version>.msi
```

The MSI installs to `C:\Program Files\stashpix`, adds that folder to the system
`PATH` (so `stashpix` works in any terminal), and creates a **Start-menu shortcut**
for the GUI. Uninstall via *Apps & features*.

User data (registry + reference index) is **not** part of the install; it lives in
`%USERPROFILE%\.stashpix\` and survives upgrades/uninstalls.

## Prerequisites

- Python 3.9+ with the package and extras installed in the build environment:

  ```powershell
  pip install -e ".[geo,api]" pyinstaller
  ```

- [WiX Toolset v4+](https://wixtoolset.org/) (a .NET global tool):

  ```powershell
  dotnet tool install --global wix
  wix extension add -g WixToolset.UI.wixext   # optional, only if you add a UI
  ```

## Build

```powershell
# from the repository root
packaging\build.ps1                 # bundle + MSI, version 1.5.0
packaging\build.ps1 -Version 1.5.0  # set the MSI version
packaging\build.ps1 -SkipBundle     # rebuild only the MSI from an existing dist/stashpix
```

Or run the steps manually:

```powershell
python -m PyInstaller packaging\pyinstaller\stashpix.spec --noconfirm
wix build packaging\wix\Package.wxs -d StageDir=dist\\stashpix -d Version=1.5.0 -o packaging\out\stashpix-1.5.0.msi
```

## Notes

- Keep the `UpgradeCode` in `wix/Package.wxs` **stable** across releases so new
  MSIs upgrade the previous install instead of installing side-by-side.
- The bundle includes OpenCV (geometry) and FastAPI/uvicorn (`stashpix serve`); make
  sure the `[geo,api]` extras are installed before building or those features
  won't be bundled.

## Linux / macOS

WiX/MSI is Windows-only, but the PyInstaller bundle itself is cross-platform. Run
the same spec on Linux/macOS to get a `dist/stashpix/` folder, then wrap it as you
prefer:

```bash
pip install -e ".[geo,api]" pyinstaller
pyinstaller packaging/pyinstaller/stashpix.spec --noconfirm
tar -czf stashpix-linux.tar.gz -C dist stashpix      # or build a .deb / .pkg / AppImage
```
