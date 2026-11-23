"""Build a Microsoft Store-ready MSIX package from a frozen Windows x64 PDFiu bundle."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_info import APP_NAME, APP_VERSION

DEFAULT_IDENTITY_NAME = "mfcb89.PDFiu"
DEFAULT_PUBLISHER = "CN=7EC350E8-B758-4C9F-9B39-895DDEFB7DAB"
DEFAULT_PUBLISHER_DISPLAY = "mfcb89"

MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">
  <Identity
    Name="{identity_name}"
    Publisher="{publisher}"
    Version="{msix_version}"
    ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>{app_name}</DisplayName>
    <PublisherDisplayName>{publisher_display}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="es-ES" />
    <Resource Language="en-US" />
  </Resources>
  <Applications>
    <Application
      Id="PDFiu"
      Executable="{app_name}.exe"
      EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{app_name}"
        Description="Lector y editor de PDF ligero y local / Lightweight local PDF reader and editor."
        BackgroundColor="#182a3d"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <uap:Extension Category="windows.fileTypeAssociation">
          <uap:FileTypeAssociation Name="pdf">
            <uap:DisplayName>Documento PDF</uap:DisplayName>
            <uap:SupportedFileTypes>
              <uap:FileType>.pdf</uap:FileType>
            </uap:SupportedFileTypes>
          </uap:FileTypeAssociation>
        </uap:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def find_makeappx():
    kits = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    candidates = sorted(kits.glob("10.*/x64/makeappx.exe"))
    if candidates:
        return candidates[-1]
    found = shutil.which("makeappx.exe")
    if found:
        return Path(found)
    raise FileNotFoundError("No se encontró makeappx.exe (instala Windows 10/11 SDK).")


def generate_store_assets(source_png, assets_dir):
    assets_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source_png) as img:
        base = img.convert("RGBA")
        for filename, size in (
            ("StoreLogo.png", (50, 50)),
            ("Square44x44Logo.png", (44, 44)),
            ("Square44x44Logo.targetsize-48.png", (48, 48)),
            ("Square44x44Logo.targetsize-256.png", (256, 256)),
            ("Square150x150Logo.png", (150, 150)),
        ):
            resized = base.resize(size, Image.Resampling.LANCZOS)
            resized.save(assets_dir / filename, format="PNG")

        wide = Image.new("RGBA", (310, 150), (24, 42, 61, 255))
        icon_tile = base.resize((104, 104), Image.Resampling.LANCZOS)
        wide.paste(icon_tile, ((310 - 104) // 2, (150 - 104) // 2), icon_tile)
        wide.save(assets_dir / "Wide310x150Logo.png", format="PNG")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True, help="Carpeta dist/PDFiu generada por build_app.py")
    parser.add_argument("--output", type=Path, required=True, help="Carpeta de salida para el archivo .msix")
    parser.add_argument("--identity-name", default=DEFAULT_IDENTITY_NAME)
    parser.add_argument("--publisher", default=DEFAULT_PUBLISHER)
    parser.add_argument("--publisher-display", default=DEFAULT_PUBLISHER_DISPLAY)
    args = parser.parse_args()

    dist_dir = args.dist.resolve()
    if not (dist_dir / f"{APP_NAME}.exe").is_file():
        parser.error(f"No se encontró {APP_NAME}.exe en {dist_dir}")

    output_dir = args.output.resolve()
    staging_dir = output_dir / "staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    shutil.copytree(
        dist_dir,
        staging_dir,
        ignore=shutil.ignore_patterns("PDFiuClose.exe", "PDFiuExplorer.exe", "default-docx-template"),
    )
    # Mark bundle so PDFiu switches Help -> Check for updates to Microsoft Store mode.
    (staging_dir / "_internal" / "msix-store.flag").write_text("store\n", encoding="utf-8")

    generate_store_assets(ROOT / "assets" / "brand" / "pdfiu-app.png", staging_dir / "Assets")

    manifest = MANIFEST_TEMPLATE.format(
        identity_name=args.identity_name,
        publisher=args.publisher,
        publisher_display=args.publisher_display,
        msix_version=f"{APP_VERSION}.0",
        app_name=APP_NAME,
    )
    (staging_dir / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    makeappx = find_makeappx()
    msix_path = output_dir / f"{APP_NAME}-{APP_VERSION}-x64.msix"
    subprocess.run(
        [str(makeappx), "pack", "/d", str(staging_dir), "/p", str(msix_path), "/o"],
        check=True,
    )
    print(f"MSIX generado correctamente: {msix_path}")


if __name__ == "__main__":
    main()
