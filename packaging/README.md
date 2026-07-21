# Packaging

Build a standalone, Python-free bundle and a Windows MSI installer.

## Output

```
dist/stego/
  ├── stego.exe        # CLI  (stego embed / extract / extract-geo / verify-visible / serve / gui)
  ├── stego-gui.exe    # desktop GUI
  └── _internal/       # bundled Python runtime, deps and data (api/static, ...)

packaging/out/Stegosuite-<version>.msi
```

The MSI installs to `C:\Program Files\Stegosuite`, adds that folder to the system
`PATH` (so `stego` works in any terminal), and creates a **Start-menu shortcut**
for the GUI. Uninstall via *Apps & features*.

User data (registry + reference index) is **not** part of the install; it lives in
`%USERPROFILE%\.stego\` and survives upgrades/uninstalls.

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
packaging\build.ps1                 # bundle + MSI, version 1.1.0
packaging\build.ps1 -Version 1.2.0  # set the MSI version
packaging\build.ps1 -SkipBundle     # rebuild only the MSI from an existing dist/stego
```

Or run the steps manually:

```powershell
python -m PyInstaller packaging\pyinstaller\stego.spec --noconfirm
wix build packaging\wix\Package.wxs -d StageDir=dist\stego -d Version=1.1.0 -o packaging\out\Stegosuite-1.1.0.msi
```

## Notes

- Keep the `UpgradeCode` in `wix/Package.wxs` **stable** across releases so new
  MSIs upgrade the previous install instead of installing side-by-side.
- The bundle includes OpenCV (geometry) and FastAPI/uvicorn (`stego serve`); make
  sure the `[geo,api]` extras are installed before building or those features
  won't be bundled.

## Linux / macOS

WiX/MSI is Windows-only, but the PyInstaller bundle itself is cross-platform. Run
the same spec on Linux/macOS to get a `dist/stego/` folder, then wrap it as you
prefer:

```bash
pip install -e ".[geo,api]" pyinstaller
pyinstaller packaging/pyinstaller/stego.spec --noconfirm
tar -czf stego-linux.tar.gz -C dist stego      # or build a .deb / .pkg / AppImage
```
