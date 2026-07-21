"""PyInstaller entry point for the CLI (`stego.exe`)."""

from stegosuite.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
