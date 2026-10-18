#!/usr/bin/env python3
import os
import re
import sys
import json
import math
import argparse
import urllib.request
import numpy as np
from scipy.fft import rfft, rfftfreq
from pydub import AudioSegment
from pydub.silence import detect_leading_silence, split_on_silence

NOTE_NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]

def hz_to_note(hz):
    if hz <= 0 or np.isnan(hz):
        return None
    h = 12 * math.log2(hz / 440.0) + 69
    midi_num = round(h)
    if midi_num < 0 or midi_num > 127:
        return None
    octave = (midi_num // 12) - 1
    note_idx = midi_num % 12
    return f"{NOTE_NAMES[note_idx]}{octave}"

def detect_single_pitch(audio_chunk, thresh=-50.0):
    if audio_chunk.dBFS < thresh:
        return None
    
    samples = np.array(audio_chunk.get_array_of_samples(), dtype=np.float32)
    if audio_chunk.channels == 2:
        samples = (samples[0::2] + samples[1::2]) / 2.0
        
    rate = audio_chunk.frame_rate
    n = len(samples)
    if n < 256: 
        return None

    fft_data = np.abs(rfft(samples))
    freqs = rfftfreq(n, d=1.0/rate)

    valid_idx = (freqs >= 40) & (freqs <= 3000)
    if not np.any(valid_idx):
        return None
        
    fft_data = fft_data[valid_idx]
    freqs = freqs[valid_idx]

    if len(fft_data) == 0:
        return None

    max_idx = np.argmax(fft_data)
    peak_freq = freqs[max_idx]
    peak_mag = fft_data[max_idx]

    total_energy = np.sum(fft_data)
    if total_energy == 0:
        return None
        
    energy_ratio = peak_mag / total_energy
    
    if energy_ratio > 0.08:
        return hz_to_note(peak_freq)
    return None

def is_chunk_blank(audio_chunk, silence_thresh=-50.0):
    return audio_chunk.dBFS < silence_thresh

def normalize_key(key):
    """
    Converts keys like "F Major", "Am", "D#" or "a# minor" into Strudel's
    scale format ("f:major", "a:minor", "d#:major"). A key with no mode is
    treated as major. Returns "" if the key can't be understood.
    """
    match = re.fullmatch(r'\s*([a-g])([#b]?)\s*[:\- ]?\s*(major|maj|minor|min|m)?\s*', str(key or ""), re.I)
    if not match:
        return ""
    note, accidental, mode = match.groups()
    is_minor = bool(mode) and mode.lower() in ("minor", "min", "m")
    return f"{note.lower()}{accidental.lower()}:{'minor' if is_minor else 'major'}"

def fetch_track_metadata(url):
    """
    Pulls the schema.org JSON-LD block that sites like Looperman embed in their
    track detail pages and extracts name/artist/bpm/key so they don't need to
    be typed in by hand.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if not ld_match:
        raise ValueError("No structured metadata block found on page")

    data = json.loads(ld_match.group(1))

    name = data.get("name", "")
    artist = (data.get("byArtist") or {}).get("name") or (data.get("creator") or {}).get("name") or ""
    if name and artist:
        name = re.sub(
            rf"\s*(?:[-–—|]\s*|\bby\s+){re.escape(artist)}\s*$",
            "",
            name,
            flags=re.I,
        ).strip()
    description = data.get("description", "")
    keywords = data.get("keywords", "")
    keyword_text = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

    bpm_match = re.search(r'(\d+(?:\.\d+)?)\s*bpm', keyword_text, re.I) or re.search(r'(\d+(?:\.\d+)?)\s*bpm', description, re.I)
    bpm = float(bpm_match.group(1)) if bpm_match else None

    key_match = re.search(r'key is ([A-G][#b]?\s*(?:major|minor|maj|min)?)', description, re.I)
    key = key_match.group(1).strip() if key_match else ""
    if not key:
        tag_block = re.search(r'class="tag-wrapper.*?class="desc-wrapper', html, re.S)
        tag_key = re.search(
            r'<a\b[^>]*>\s*Key\s*:\s*([A-G][#b]?\s*(?:major|minor|m)?)\s*</a>',
            tag_block.group(0),
            re.I,
        ) if tag_block else None
        if tag_key:
            key = tag_key.group(1).strip()
            if re.fullmatch(r"[A-G][#b]?m", key, re.I):
                key = f"{key[:-1]} minor"
    gender_match = re.search(r'\b(male|female|non-binary|nonbinary)\b', keyword_text, re.I)
    genre = data.get("genre", "")
    if isinstance(genre, list):
        genre = ", ".join(str(value) for value in genre)

    return {
        "name": name,
        "artist": artist,
        "bpm": bpm,
        "key": key,
        "vocal_gender": gender_match.group(1).title() if gender_match else "",
        "genre": str(genre),
        "source_url": data.get("url", url),
    }

def update_readme(output_dir, metadata):
    """
    Generates or parses an existing README.md file to output an up-to-date
    Markdown log layout compiling tracks, keys, and usage credits.
    """
    readme_path = os.path.join(output_dir, "README.md")
    
    # Header templates
    header_title = "# Strudel Sample Vault Catalog\n\n"
    table_header = "| Track Identifier | BPM | Key | Vocal Gender | Genre | Credit / Attribution | Source Reference URL |\n| :--- | :---: | :---: | :---: | :--- | :--- | :--- |\n"
    
    # Build dictionary rows
    rows = {}
    
    # Read existing table if file is present to update records in place safely
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            if line.startswith("|") and not "Track Identifier" in line and not ":---" in line:
                parts = [p.strip() for p in line.split("|")][1:-1]
                if len(parts) >= 5:
                    track_id = parts[0].strip("*")
                    if len(parts) >= 7:
                        bpm, key, vocal_gender, genre, credit, source_url = parts[1:7]
                    else:
                        bpm, key, credit, source_url = parts[1:5]
                        vocal_gender, genre = "UNKNOWN", "UNKNOWN"
                    key = normalize_key(key) or "unknown"
                    rows[track_id] = {
                        "bpm": bpm,
                        "key": key,
                        "vocal_gender": vocal_gender,
                        "genre": genre,
                        "credit": credit,
                        "source_url": source_url,
                    }
                    
    # Generate / Update rows from current metadata pool state
    for track_id, meta in metadata.items():
        source_url = meta.get("source_url", "")
        url_md = f"[Source Link]({source_url})" if source_url else "N/A"
        rows[track_id] = {
            "bpm": meta.get("bpm", "UNKNOWN"),
            "key": normalize_key(meta.get("key")) or "unknown",
            "vocal_gender": meta.get("vocal_gender") or "UNKNOWN",
            "genre": meta.get("genre") or "UNKNOWN",
            "credit": meta.get("credit") or "Unknown",
            "source_url": url_md,
        }

    # Write out cleanly structured document
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(header_title)
        f.write("This file is automatically managed by the CLI processing tool to log sample origins for simple copy-pasting into track releases.\n\n")
        f.write(table_header)
        for track_id in sorted(rows.keys()):
            row = rows[track_id]
            f.write(
                f"| **{track_id}** | {row['bpm']} | {row['key']} | "
                f"{row['vocal_gender']} | {row['genre']} | {row['credit']} | "
                f"{row['source_url']} |\n"
            )
            
    print(f"Updated cleartext tracking index documentation at: {readme_path}")

def load_master_data(json_path):
    master_data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                master_data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Could not parse JSON data in '{json_path}': {exc}") from exc

    if not isinstance(master_data, dict):
        raise ValueError(f"Expected a JSON object in '{json_path}'.")

    if "_base" not in master_data:
        master_data["_base"] = "http://localhost:5432/"
    if "_metadata" not in master_data:
        master_data["_metadata"] = {}
    elif not isinstance(master_data["_metadata"], dict):
        raise ValueError(f"Expected '_metadata' in '{json_path}' to be an object.")
    return master_data

def is_unknown_metadata(value):
    return value is None or (
        isinstance(value, str)
        and value.strip().casefold() in {"", "unknown", "n/a"}
    )

def refresh_unknown_metadata(metadata):
    updated_tracks = 0
    failed_tracks = 0
    fields_updated = 0
    metadata_fields = {
        "bpm": "bpm",
        "key": "key",
        "vocal_gender": "vocal_gender",
        "genre": "genre",
        "credit": "artist",
    }

    for track_id, track_metadata in metadata.items():
        unknown_fields = [
            field for field in metadata_fields
            if is_unknown_metadata(track_metadata.get(field))
        ]
        if not unknown_fields:
            continue

        source_url = track_metadata.get("source_url")
        if is_unknown_metadata(source_url):
            print(f"Warning: cannot refresh '{track_id}'; no source URL is recorded.")
            failed_tracks += 1
            continue

        try:
            scraped = fetch_track_metadata(source_url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"Warning: could not refresh '{track_id}' from '{source_url}': {exc}")
            failed_tracks += 1
            continue

        track_updated = False
        for field in unknown_fields:
            value = scraped.get(metadata_fields[field])
            if field == "key":
                value = normalize_key(value)
            if is_unknown_metadata(value):
                continue
            track_metadata[field] = value
            fields_updated += 1
            track_updated = True

        if track_updated:
            updated_tracks += 1
        unresolved_fields = [
            field for field in unknown_fields
            if is_unknown_metadata(track_metadata.get(field))
        ]
        if unresolved_fields:
            print(
                f"Warning: source page did not provide usable values for "
                f"{', '.join(unresolved_fields)} on '{track_id}'."
            )

    return updated_tracks, failed_tracks, fields_updated

def process_cli():
    parser = argparse.ArgumentParser(
        description="Slice stem files with gap-aware pitch detection and maintain a markdown README.md log repository file."
    )
    parser.add_argument("--file", help="Path to your audio stem file (not needed for metadata-only modes)")
    metadata_modes = parser.add_mutually_exclusive_group()
    metadata_modes.add_argument("--metadata-only", action="store_true", help="Only update the JSON metadata and README table; skip all audio processing")
    metadata_modes.add_argument("--refresh-metadata", action="store_true", help="Refetch missing or unknown metadata from saved source URLs; skip audio processing")
    parser.add_argument("--bpm", type=float, default=None, help="Tempo of the track (auto-filled from --url if omitted)")
    parser.add_argument("--key", default=None, help="The global musical key of the stem track (auto-filled from --url if omitted)")
    parser.add_argument("--name", help="Custom root name variable (auto-filled from --url if omitted)")
    parser.add_argument("--beats", type=int, default=4, help="Beats per bar")
    parser.add_argument("--long-bars", type=int, default=4, help="Bars per long section")
    parser.add_argument("--thresh", type=float, default=-50.0, help="Silence threshold level in dBFS")
    parser.add_argument("--trim-thresh", type=float, default=-90.0,help="Override --thresh only when trimming leading silence")
    parser.add_argument("--click-bars", type=float, default=0.0, help="Length in bars of a leading click/count-in to discard; the grid is aligned to its end (0 = no click)")
    parser.add_argument("--min-silence-len", type=int, default=100, help="Minimum length of silence to split short notes (in ms)")
    parser.add_argument("--json-path", help="Path to your master JSON structure file (defaults to <output-dir>/strudel.json)")
    parser.add_argument("--output-dir", default="strudel_samples", help="Root directory folder output destination")
    parser.add_argument("--url", default="", help="Origin attribution URL link")
    parser.add_argument("--credit", default="", help="Copyright or attribution details")

    args = parser.parse_args()
    if args.json_path is None:
        args.json_path = os.path.join(args.output_dir, "strudel.json")

    if not args.metadata_only and not args.refresh_metadata:
        if not args.file:
            print("Error: --file is required unless --metadata-only or --refresh-metadata is set.")
            sys.exit(1)
        if not os.path.exists(args.file):
            print(f"Error: Target path '{args.file}' does not exist.")
            sys.exit(1)

    if args.refresh_metadata:
        master_data = load_master_data(args.json_path)
        updated, failed, fields_updated = refresh_unknown_metadata(master_data["_metadata"])
        with open(args.json_path, "w") as f:
            json.dump(master_data, f, indent=2, sort_keys=True)
        update_readme(args.output_dir, master_data["_metadata"])
        print(
            f"\nMetadata refresh complete: {updated} track(s) updated, "
            f"{fields_updated} field(s) filled, {failed} track(s) could not be refreshed."
        )
        return

    scraped = None
    if args.url:
        try:
            scraped = fetch_track_metadata(args.url)
            print(f"Fetched metadata from URL: '{scraped['name']}' by {scraped['artist'] or 'Unknown'}")
        except Exception as e:
            print(f"Warning: could not fetch metadata from '{args.url}' ({e}); falling back to manual arguments.")

    if args.bpm is None:
        if scraped and scraped.get("bpm"):
            args.bpm = scraped["bpm"]
        else:
            print("Error: --bpm was not provided and could not be determined from --url.")
            sys.exit(1)

    if not args.name and scraped and scraped.get("name"):
        args.name = scraped["name"]

    raw_key = args.key or (scraped.get("key") if scraped else "")
    args.key = normalize_key(raw_key)
    if raw_key and not args.key:
        print(f"Warning: could not understand key '{raw_key}'; storing as unknown.")
    args.key = args.key or "unknown"

    if not args.credit and scraped and scraped.get("artist"):
        args.credit = scraped["artist"]

    if args.name:
        raw_name = args.name
    elif args.file:
        raw_name = os.path.splitext(os.path.basename(args.file))[0]
    else:
        print("Error: --metadata-only needs --name or a --url to determine the track name.")
        sys.exit(1)
    base_name = raw_name.strip().lower().replace(" ", "_")

    track_metadata = {
        "bpm": args.bpm,
        "key": args.key,
        "vocal_gender": (scraped.get("vocal_gender") if scraped else "") or "unknown",
        "genre": (scraped.get("genre") if scraped else "") or "unknown",
        "beats_per_bar": args.beats,
        "source_url": args.url,
        "credit": args.credit
    }

    if args.metadata_only:
        master_data = load_master_data(args.json_path)
        if f"{base_name}_short" not in master_data:
            print(f"Warning: no existing samples found for '{base_name}'; only metadata will be written.")
        master_data["_metadata"][base_name] = track_metadata
        with open(args.json_path, "w") as f:
            json.dump(master_data, f, indent=2, sort_keys=True)
        update_readme(args.output_dir, master_data["_metadata"])
        print(f"\nUpdated metadata for '{base_name}' in '{args.json_path}' (no audio processed).")
        return

    folder_short = f"{base_name}_short"
    folder_bar = f"{base_name}_bar"
    folder_long = f"{base_name}_long"

    os.makedirs(os.path.join(args.output_dir, folder_short), exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, folder_bar), exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, folder_long), exist_ok=True)

    ms_per_beat = (60 / args.bpm) * 1000
    ms_per_bar = ms_per_beat * args.beats
    ms_per_long = ms_per_bar * args.long_bars

    print(f"Opening file: {args.file}")
    audio = AudioSegment.from_file(args.file)
    
    if args.click_bars > 0:
        # The click defines the grid, so cut exactly its length and skip silence trimming
        start_trim_ms = int(round(args.click_bars * ms_per_bar))
        if start_trim_ms >= len(audio):
            print(f"Error: click length ({start_trim_ms}ms) is not shorter than the audio ({len(audio)}ms).")
            sys.exit(1)
        print(f"Discarding leading click: {args.click_bars} bar(s) = {start_trim_ms}ms dropped.")
    else:
        trim_thresh = args.thresh if args.trim_thresh is None else args.trim_thresh
        start_trim_ms = detect_leading_silence(audio, silence_threshold=trim_thresh)
        print(f"Stripping leading space: {start_trim_ms}ms dropped.")
    aligned_audio = audio[start_trim_ms:]
    total_ms = len(aligned_audio)
    file_ext = os.path.splitext(args.file)[1].replace(".", "")

    samples_short = []
    samples_bar = []
    samples_long = []

    # 1. PROCESS SHORTS (Gap-based segmentation)
    print("Extracting dynamic shorts using gap analysis...")
    short_chunks = split_on_silence(
        aligned_audio, 
        min_silence_len=args.min_silence_len, 
        silence_thresh=args.thresh,
        keep_silence=50 
    )
    
    for i, chunk in enumerate(short_chunks):
        if len(chunk) > 0 and not is_chunk_blank(chunk, args.thresh):
            filename = f"short_{str(i).zfill(3)}.{file_ext}"
            rel_path = f"{folder_short}/{filename}"
            chunk.export(os.path.join(args.output_dir, folder_short, filename), format=file_ext)
            
            detected_note = detect_single_pitch(chunk, args.thresh)
            if detected_note:
                samples_short.append({detected_note: rel_path})
            else:
                samples_short.append(rel_path)

    # 2. PROCESS BARS (Strict Grid)
    print("Slicing rigid bars...")
    total_bars = math.ceil(total_ms / ms_per_bar)
    for i in range(total_bars):
        chunk = aligned_audio[int(i * ms_per_bar) : int((i + 1) * ms_per_bar)]
        if len(chunk) > 0 and not is_chunk_blank(chunk, args.thresh):
            filename = f"bar_{str(i).zfill(2)}.{file_ext}"
            rel_path = f"{folder_bar}/{filename}"
            chunk.export(os.path.join(args.output_dir, folder_bar, filename), format=file_ext)
            samples_bar.append(rel_path)

    # 3. PROCESS LONGS (Strict Grid)
    print("Slicing rigid long phrases...")
    total_longs = math.ceil(total_ms / ms_per_long)
    for i in range(total_longs):
        chunk = aligned_audio[int(i * ms_per_long) : int((i + 1) * ms_per_long)]
        if len(chunk) > 0 and not is_chunk_blank(chunk, args.thresh):
            filename = f"long_{str(i).zfill(2)}.{file_ext}"
            rel_path = f"{folder_long}/{filename}"
            chunk.export(os.path.join(args.output_dir, folder_long, filename), format=file_ext)
            samples_long.append(rel_path)

    # 4. MASTER JSON STORAGE UPDATE
    master_data = load_master_data(args.json_path)

    master_data[folder_short] = samples_short
    master_data[folder_bar] = samples_bar
    master_data[folder_long] = samples_long

    master_data["_metadata"][base_name] = track_metadata

    with open(args.json_path, "w") as f:
        json.dump(master_data, f, indent=2, sort_keys=True)

    # 5. WRITE MARKDOWN README COMPILATION DOCUMENTATION
    update_readme(args.output_dir, master_data["_metadata"])

    print(f"\nSuccessfully stored '{base_name}' in '{args.json_path}'!")

if __name__ == "__main__":
    process_cli()
