"""
Intip isi raw-audio-indonesia.zip (Zenodo) TANPA mengunduh seluruh zip.

Install:  pip install remotezip requests
Jalankan: python3 inspect_zip.py

Hasil: ringkasan di layar + file zip_listing.csv (daftar lengkap).
Kirim ringkasan di layar ke Claude (cukup copy-paste).
"""
import csv, os, sys
from collections import Counter, defaultdict

# Record Zenodo = angka di akhir DOI 10.5281/zenodo.14841479
URL = "https://zenodo.org/records/14841479/files/raw-audio-indonesia.zip?download=1"


def summarize(infos, depth=2, examples=3):
    """infos: list of (name, size). Ringkas per folder sampai kedalaman `depth`."""
    ext = Counter()
    groups = defaultdict(lambda: [0, 0, []])  # key -> [jumlah, total_byte, contoh]
    for name, size in infos:
        if name.endswith("/"):
            continue
        ext[os.path.splitext(name)[1].lower() or "(tanpa ekstensi)"] += 1
        parts = name.split("/")
        key = "/".join(parts[:-1][:depth]) or "(root)"
        g = groups[key]
        g[0] += 1
        g[1] += size
        if len(g[2]) < examples:
            g[2].append(parts[-1])
    return ext, groups


def main():
    import requests
    from remotezip import RemoteZip

    # 1) Tes range request
    r = requests.get(URL, headers={"Range": "bytes=0-0"}, stream=True,
                     allow_redirects=True, timeout=60)
    code, ctype, clen = r.status_code, r.headers.get("Content-Type"), r.headers.get("Content-Range")
    final = r.url
    r.close()
    print(f"status={code}  range_didukung={code == 206}  content-range={clen}")
    if code != 206:
        print(f"URL akhir: {final}\nContent-Type: {ctype}")
        sys.exit("Range request tidak jalan. Kirim output ini ke Claude.")

    # 2) Baca daftar isi zip (hanya central directory, bukan seluruh file)
    with RemoteZip(final) as z:
        infos = [(i.filename, i.file_size) for i in z.infolist()]
    print(f"\nTotal entri: {len(infos)}")

    with open("zip_listing.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "size_bytes"])
        w.writerows(infos)

    ext, groups = summarize(infos)
    print("\nEkstensi file:", dict(ext.most_common(8)))
    print(f"\nFolder (kedalaman 2): {len(groups)} kelompok")
    for key in sorted(groups)[:60]:
        n, b, ex = groups[key]
        print(f"  {key:<55} {n:>7} file  {b / 1e9:6.2f} GB  contoh: {ex}")
    if len(groups) > 60:
        print(f"  ... dan {len(groups) - 60} kelompok lain (lihat zip_listing.csv)")
    print("\nSelesai. Copy-paste semua output di atas ke Claude.")


if __name__ == "__main__":
    main()