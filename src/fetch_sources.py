"""Download the source articles into data/sources/ (not committed; see .gitignore).

Several publishers block scripted downloads; for those the URL is an open-access
mirror (publisher CDN or an Internet Archive snapshot) of the same CC-BY article.
SHA-256 checksums of the copies used for the paper are in data/sources.sha256.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sources"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/{}/fullTextXML"

SOURCES = {
    "P01_soundhar2019.xml": EPMC.format("PMC6369405"),
    "P21_bahgat2019.xml": EPMC.format("PMC6556808"),
    "H05_jagdale2025.xml": EPMC.format("PMC12361545"),
    "H17_surani2025.xml": EPMC.format("PMC12700910"),
    "P06_fatatit2021.pdf": "https://mjst.ustp.edu.ph/index.php/mjst/article/download/779/177",
    "P10_akincioglu2022.pdf": "https://casopisi.junis.ni.ac.rs/index.php/FUMechEng/article/download/7289/4087",
    "P12_reddy2016.pdf": "http://www.ijettjournal.org/assets/year/2016/volume-31/number-2/IJETT-V31P219.pdf",
    "P13_ram2025.pdf": "https://web.archive.org/web/20260731101835id_/https://link.springer.com/content/pdf/10.1186/s44147-025-00614-y.pdf",
    "H04_chandrashekarappa2021.pdf": "https://mdpi-res.com/d_attachment/metals/metals-11-00419/article_deploy/metals-11-00419.pdf",
    "H18_hassan2023.pdf": "https://mdpi-res.com/d_attachment/metals/metals-13-01964/article_deploy/metals-13-01964.pdf",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        dest = OUT / name
        if dest.exists():
            continue
        print("fetching", name)
        subprocess.run(["curl", "-sL", "--retry", "3", "-A", "Mozilla/5.0", "-o", str(dest), url], check=True)
    res = subprocess.run(["sha256sum", "-c", "../sources.sha256"], cwd=OUT, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode:
        sys.exit("checksum mismatch: a source file differs from the copy used in the paper")


if __name__ == "__main__":
    main()
