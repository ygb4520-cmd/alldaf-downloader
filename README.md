# AllDaf Shiur Downloader

Download every shiur by one speaker on one mesechta from [alldaf.org](https://alldaf.org), in one click.
Files are saved to `<folder>\<speaker>\<mesechta>\`.

## Get it

Download `alldaf_downloader.exe` from the [latest release](https://github.com/ygb4520-cmd/alldaf-downloader/releases/latest)
and run it. Windows may show a SmartScreen warning because the exe isn't code-signed; each release also has a
`.sha256` file so you can check the download. The app updates itself when a new release comes out.

Or run from source (Python 3.8+, nothing to install): `python alldaf_downloader.py`

## Using it

1. Pick a **speaker**. Use **Add** for others: type their name and choose from the matches (or paste the link/ID from their alldaf.org author page).
2. Pick a **mesechta** (type to search; recently used ones are on top) and **Bavli / Yerushalmi / Both**.
3. Optionally set a **Dapim** range (e.g. 20 to 40; blank = all).
4. Choose a **Save to** folder and press **Start download**.

Shiurim already in the folder are skipped, so you can run it again later to pick up new ones.
Downloads run 3 at a time, and a dropped connection or **Stop** is continued from where it left off next time.
**Open folder** jumps to the results.

Only tick **Skip SSL check** if a work/school proxy breaks secure connections. It is off by default.

## Developing

```
python -m unittest discover -s tests
```

Publishing a GitHub release builds the exe (PyInstaller, pinned) and attaches it with its SHA-256 checksum;
the version number is taken from the release tag.

This tool talks to alldaf.org's unofficial API, so a change on their side can break it; the app shows a clear
message if the reply stops looking right.
