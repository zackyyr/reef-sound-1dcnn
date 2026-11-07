"""
Sampler untuk raw-audio-indonesia.zip (Zenodo 14841479), TANPA mengunduh seluruh zip.

Tafsiran nama file (sudah dicocokkan dengan paper: H+D = 3.338 file vs 3.335 di paper):
  BaF1.1055H.1678278701.180827.NT1055.wav
  Ba   = pulau (Ba=Badi, Bo=Bontosua, Sa=Salisih)
  F    = fase bulan (F/N, dugaan full/new moon)
  1    = hari ke-n
  1055 = jam mulai sesi 1 jam (HHMM);  H = habitat (H=healthy, D=degraded, R=restored)
Hanya H dan D yang diambil. "Lokasi" = pulau + habitat, contoh Ba-H, Bo-H, Bo-D, Sa-D.

Install:  pip install remotezip requests numpy scipy soundfile
Jalankan: python3 sample_indonesia2018.py --dry-run     (lihat rencana, belum mengunduh)
          python3 sample_indonesia2018.py               (ambil sampel)
Aman dihentikan dan dijalankan ulang: file yang sudah selesai dilewati.
"""
import argparse, csv, os, random, re, sys, time
from collections import defaultdict
from math import gcd

URL = "https://zenodo.org/records/14841479/files/raw-audio-indonesia.zip?download=1"
KEEP = {"H": "healthy", "D": "degraded"}       # R (restored) dilepas dulu
ISLANDS = {"Ba": "Badi", "Bo": "Bontosua", "Sa": "Salisih"}
TARGET_SR = 16000
CLIP_SECONDS = 5
SEED = 42

NAME_RE = re.compile(
    r"^(?P<island>[A-Za-z]{2})(?P<moon>[A-Za-z])(?P<day>\d+)\."
    r"(?P<start>\d{4})(?P<hab>[A-Za-z])\.(?P<serial>\d+)\."
    r"(?P<date>\d{6})\.(?P<nt>[A-Za-z]*\d+)\.wav$")


def parse_name(path):
    m = NAME_RE.match(os.path.basename(path))
    if not m:
        return None
    d = m.groupdict()
    d["site"] = f"{d['island']}-{d['hab']}"
    d["session"] = f"{d['date']}_{d['start']}{d['hab']}"
    return d


def select_files(entries, n, seed=SEED):
    """entries: list of (zip_name, info). Round-robin antar sesi 1 jam agar tersebar merata."""
    by_session = defaultdict(list)
    for name, info in entries:
        by_session[info["session"]].append(name)
    rng = random.Random(seed)
    sessions = sorted(by_session)
    for s in sessions:
        rng.shuffle(by_session[s])
    chosen = []
    while len(chosen) < n and any(by_session[s] for s in sessions):
        for s in sessions:
            if by_session[s] and len(chosen) < n:
                chosen.append(by_session[s].pop())
    return chosen


def read_wav(path):
    """Kembalikan (mono float32, sample_rate)."""
    import numpy as np
    try:
        import soundfile as sf
        x, sr = sf.read(path, dtype="float32")
    except ImportError:
        from scipy.io import wavfile
        sr, x = wavfile.read(path)
        if x.dtype.kind == "i":
            x = x.astype("float32") / np.iinfo(x.dtype).max
        else:
            x = x.astype("float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x, sr


def to_clips(x, sr, seconds=CLIP_SECONDS, target_sr=TARGET_SR):
    """Resample ke target_sr lalu potong klip tanpa tumpang tindih. Kembalikan list array int16."""
    import numpy as np
    from scipy.signal import resample_poly
    if sr != target_sr:
        g = gcd(sr, target_sr)
        x = resample_poly(x, target_sr // g, sr // g).astype("float32")
    step = int(target_sr * seconds)
    clips = []
    for i in range(len(x) // step):
        seg = np.clip(x[i * step:(i + 1) * step], -1.0, 1.0)
        clips.append((seg * 32767).astype("int16"))
    return clips


def write_wav(path, arr, sr=TARGET_SR):
    from scipy.io import wavfile
    wavfile.write(path, sr, arr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="jumlah file 1 menit per lokasi")
    ap.add_argument("--out", default="reef_sample")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import requests
    from remotezip import RemoteZip

    r = requests.get(URL, headers={"Range": "bytes=0-0"}, stream=True, timeout=60)
    ok = r.status_code == 206
    r.close()
    print(f"range_didukung={ok}")
    if not ok:
        sys.exit("Range request tidak jalan.")

    with RemoteZip(URL) as z:
        names = [i.filename for i in z.infolist() if i.filename.lower().endswith(".wav")]

    by_site, skipped = defaultdict(list), 0
    for nm in names:
        info = parse_name(nm)
        if info is None:
            skipped += 1
            continue
        if info["hab"] in KEEP and info["island"] in ISLANDS:
            by_site[info["site"]].append((nm, info))
    if skipped:
        print(f"PERINGATAN: {skipped} nama file tidak cocok pola, dilewati.")

    plan = {}
    print(f"\n{'lokasi':<8}{'tersedia':>10}{'diambil':>10}  sesi")
    for site in sorted(by_site):
        chosen = select_files(by_site[site], args.n)
        lookup = dict(by_site[site])
        plan[site] = {nm: lookup[nm] for nm in chosen}
        sessions = len({i["session"] for i in plan[site].values()})
        print(f"{site:<8}{len(by_site[site]):>10}{len(chosen):>10}  {sessions}")
    total = sum(len(v) for v in plan.values())
    print(f"\nTotal {total} file, perkiraan unduhan tidak terkompresi ~{total * 5.76 / 1000:.1f} GB")
    if args.dry_run:
        print("Dry run selesai. Jalankan tanpa --dry-run untuk mengambil data.")
        return

    os.makedirs(args.out, exist_ok=True)
    meta_path = os.path.join(args.out, "metadata.csv")
    done = set()
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            done = {row["src_file"] for row in csv.DictReader(f)}
    new_file = not os.path.exists(meta_path)
    cols = ["path", "site", "island", "label", "date", "moon", "session", "nt", "src_file"]
    meta = open(meta_path, "a", newline="")
    w = csv.writer(meta)
    if new_file:
        w.writerow(cols)

    tmp = os.path.join(args.out, "_tmp")
    os.makedirs(tmp, exist_ok=True)
    z = RemoteZip(URL)
    first = True
    for site in sorted(plan):
        clip_dir = os.path.join(args.out, "clips", site)
        os.makedirs(clip_dir, exist_ok=True)
        items = [(nm, inf) for nm, inf in plan[site].items() if nm not in done]
        print(f"[{site}] {len(items)} file baru")
        for i, (nm, inf) in enumerate(items, 1):
            for attempt in range(1, 4):
                try:
                    z.extract(nm, tmp)
                    break
                except Exception as e:
                    print(f"  gagal ({e}), coba lagi {attempt}/3")
                    time.sleep(5)
                    z = RemoteZip(URL)
            else:
                print(f"  DILEWATI: {nm}")
                continue
            raw = os.path.join(tmp, nm)
            x, sr = read_wav(raw)
            if first:
                print(f"  info file pertama: sample_rate={sr} Hz, durasi={len(x) / sr:.1f} s")
                first = False
            rows = []
            for k, clip in enumerate(to_clips(x, sr)):
                stem = f"{site}_{inf['date']}_{inf['start']}_{inf['nt']}_c{k:02d}.wav"
                p = os.path.join(clip_dir, stem)
                write_wav(p, clip)
                rows.append([p, site, ISLANDS[inf["island"]], KEEP[inf["hab"]], inf["date"],
                             inf["moon"], inf["session"], inf["nt"], nm])
            w.writerows(rows)
            meta.flush()
            os.remove(raw)
            if i % 25 == 0:
                print(f"  {i}/{len(items)}")
    z.close()
    meta.close()
    print(f"Selesai. Metadata: {meta_path}")


if __name__ == "__main__":
    main()