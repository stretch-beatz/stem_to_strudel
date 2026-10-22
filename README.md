# stem_to_strudel

Slice an audio stem into short vocal/sample chunks, fixed-length bars, and longer phrases for use in Strudel. The script also detects a likely pitch for short chunks and updates a JSON sample index and a Markdown catalog.

## Requirements

- Python 3
- FFmpeg available on your `PATH` for audio formats that require it (including MP3)
- Python dependencies from `requirements.txt`

Install the Python dependencies from the project directory:

```bash
python3 -m pip install -r requirements.txt
```

## Basic usage

Run the script with an audio file and a source URL:

```bash
python3 stem_to_strudel.py \
  --file "/path/to/vocal.wav" \
  --url "https://www.looperman.com/acapellas/detail/20691/fatafat-95bpm-pop-acapella"
```

When the page provides structured metadata, the script fills in the BPM, track name, key, artist credit, vocal gender, and genre. For fetched titles, a trailing `by Artist` suffix is treated as attribution, and a title emphasized with asterisks is used as the track name (for example, `AMVIS - *SoCold* - Hybrid Trap Type Vocals` becomes `SoCold`). You can provide `--bpm`, `--key`, `--name`, or `--credit` to supply or override those values. BPM is required if it cannot be fetched from the URL. If the key or vocal metadata is unavailable, the catalog records it as unknown.

You can also run it without a source URL by entering the BPM yourself:

```bash
python3 stem_to_strudel.py \
  --file "/path/to/vocal.wav" \
  --bpm 95 \
  --key "F major" \
  --name fatafat \
  --credit "Artist name"
```

## Leading click track

If your stem starts with a click or count-in (handy for lining it up in a DAW), use `--click-bars` to discard it. The value is the click's length in bars at the track BPM (decimals allowed, e.g. `0.5`, and `--beats` sets beats per bar):

```bash
python3 stem_to_strudel.py --file "/path/to/vocal.wav" --bpm 95 --click-bars 2
```

The script cuts exactly that many bars from the start, so bar and long slices stay aligned to the grid. Leading-silence trimming is skipped while a click is set, since it would shift the grid. Without `--click-bars`, leading silence is trimmed as before.

## Metadata only

To refresh a track's metadata (key, genre, vocal gender, credit, etc.) without touching any audio, add `--metadata-only`. It only updates `strudel.json` metadata and the catalog table; existing slices and sample lists are left alone, and `--file` isn't needed. The track name comes from `--name` or the `--url` page, so it must match the original run.

```bash
python3 stem_to_strudel.py --metadata-only \
  --url "https://www.looperman.com/acapellas/detail/18631/demasiado-pronto-ashesndreams-93bpm-reggaeton-acapella" \
  --output-dir /path/to/strudel-sample-backup
```

## Refresh unknown metadata

The JSON index records each track's source URL, so you can rescan tracks whose BPM, key, vocal gender, genre, or credit is blank or marked `unknown`/`UNKNOWN`. The refresh fills only unknown fields, leaves known values and sample paths untouched, and regenerates the catalog table:

```bash
python3 stem_to_strudel.py --refresh-metadata \
  --output-dir /path/to/strudel-sample-backup
```

Tracks without a saved source URL are skipped with a warning. Use `--json-path` if the index is stored somewhere other than `<output-dir>/strudel.json`.

## Rebuild the catalog

Regenerate `README.md` from the JSON index without processing audio or fetching metadata:

```bash
python3 stem_to_strudel.py --rebuild-readme \
  --output-dir /path/to/strudel-sample-backup
```

Use `--json-path` if the index is stored somewhere other than `<output-dir>/strudel.json`. The command requires the JSON index to exist.

## Output

By default, files are written under `strudel_samples/`. The script creates:

- `<name>_short/` — chunks split around detected silences; likely pitches are added to the JSON index when detected.
- `<name>_bar/` — chunks aligned to a fixed number of beats per bar.
- `<name>_long/` — chunks aligned to a fixed number of bars.
- `strudel.json` — sample paths and metadata, including BPM, key, vocal gender, genre, credit, and source URL.
- `README.md` — a Markdown catalog generated from `strudel.json` metadata, sorted by genre, numeric BPM, key, then track name. The JSON is the source of truth; manual edits to the generated catalog are overwritten.

The default sample name is based on the source track title when available (the uploader/artist suffix is removed), or the audio filename otherwise. Use `--name` to set it explicitly. Use `--output-dir` to change the output directory. Use `--json-path` to store the JSON index at a different path.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `--file` | Required (unless a metadata-only mode is used) | Audio stem to process. |
| `--metadata-only` | Off | Update only the JSON metadata and catalog table; no audio processing. |
| `--refresh-metadata` | Off | Rescan source URLs and fill missing/unknown JSON metadata; no audio processing. |
| `--rebuild-readme` | Off | Regenerate the README catalog from JSON metadata only; no audio processing or metadata fetching. |
| `--url` | None | Source URL; used to fetch track metadata and attribution. |
| `--bpm` | From URL | Track tempo. Required if it cannot be fetched. |
| `--key` | From URL or `unknown` | Track key (e.g. `F major`, `Am`, `a#:minor`). Stored in Strudel format, e.g. `f:major`; a key with no mode is treated as major. |
| `--name` | From URL or filename | Name used for output folders and catalog entry. |
| `--credit` | Artist from URL | Attribution text for the catalog. |
| `--output-dir` | `strudel_samples` | Root output directory. |
| `--json-path` | `<output-dir>/strudel.json` | Path to the master JSON index. |
| `--beats` | `4` | Beats per bar. |
| `--long-bars` | `4` | Bars per long section. |
| `--thresh` | `-50` dBFS | Silence threshold for splitting, blank-chunk checks, and pitch detection. |
| `--click-bars` | `0` (off) | Length in bars of a leading click to discard; skips silence trimming. |
| `--trim-thresh` | `-90` dBFS | Silence threshold used only to trim leading silence. |
| `--min-silence-len` | `100` ms | Minimum silence duration used to split short chunks. |

For the full command-line help, run:

```bash
python3 stem_to_strudel.py --help
```
