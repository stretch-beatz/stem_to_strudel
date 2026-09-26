#!/usr/bin/env python3
import os
import sys
import json
import math
import argparse
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

def update_readme(output_dir, metadata):
    """
    Generates or parses an existing README.md file to output an up-to-date
    Markdown log layout compiling tracks, keys, and usage credits.
    """
    readme_path = os.path.join(output_dir, "README.md")
    
    # Header templates
    header_title = "# Strudel Sample Vault Catalog\n\n"
    table_header = "| Track Identifier | BPM | Key | Credit / Attribution | Source Reference URL |\n| :--- | :---: | :---: | :--- | :--- |\n"
    
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
                    track_id = parts[0]
                    rows[track_id] = line
                    
    # Generate / Update rows from current metadata pool state
    for track_id, meta in metadata.items():
        url_md = f"[Source Link]({meta['source_url']})" if meta['source_url'] else "N/A"
        credit_str = meta['credit'] if meta['credit'] else "Unknown"
        rows[track_id] = f"| **{track_id}** | {meta['bpm']} | {meta['key'].upper()} | {credit_str} | {url_md} |\n"

    # Write out cleanly structured document
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(header_title)
        f.write("This file is automatically managed by the CLI processing tool to log sample origins for simple copy-pasting into track releases.\n\n")
        f.write(table_header)
        for track_id in sorted(rows.keys()):
            f.write(rows[track_id])
            
    print(f"Updated cleartext tracking index documentation at: {readme_path}")

def process_cli():
    parser = argparse.ArgumentParser(
        description="Slice stem files with gap-aware pitch detection and maintain a markdown README.md log repository file."
    )
    parser.add_argument("--file", required=True, help="Path to your audio stem file")
    parser.add_argument("--bpm", type=float, required=True, help="Tempo of the track")
    parser.add_argument("--key", default="unknown", help="The global musical key of the stem track")
    parser.add_argument("--name", help="Custom root name variable")
    parser.add_argument("--beats", type=int, default=4, help="Beats per bar")
    parser.add_argument("--long-bars", type=int, default=4, help="Bars per long section")
    parser.add_argument("--thresh", type=float, default=-50.0, help="Silence threshold level in dBFS")
    parser.add_argument("--min-silence-len", type=int, default=100, help="Minimum length of silence to split short notes (in ms)")
    parser.add_argument("--json-path", default="strudel.json", help="Path to your master JSON structure file")
    parser.add_argument("--output-dir", default="strudel_samples", help="Root directory folder output destination")
    parser.add_argument("--url", default="", help="Origin attribution URL link")
    parser.add_argument("--credit", default="", help="Copyright or attribution details")

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: Target path '{args.file}' does not exist.")
        sys.exit(1)

    raw_name = args.name if args.name else os.path.splitext(os.path.basename(args.file))[0]
    base_name = raw_name.strip().lower().replace(" ", "_")
    
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
    
    start_trim_ms = detect_leading_silence(audio, silence_thresh=args.thresh)
    print(f"Stripping leading space: {start_trim_ms}ms dropped.")
    aligned_audio = audio[start_trim_ms:]
    total_ms = len(aligned_audio)
    file_ext = os.path.splitext(args.file).replace(".", "")

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
            filename = f"short_{str(i + 1).zfill(3)}.{file_ext}"
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
            filename = f"bar_{str(i + 1).zfill(2)}.{file_ext}"
            rel_path = f"{folder_bar}/{filename}"
            chunk.export(os.path.join(args.output_dir, folder_bar, filename), format=file_ext)
            samples_bar.append(rel_path)

    # 3. PROCESS LONGS (Strict Grid)
    print("Slicing rigid long phrases...")
    total_longs = math.ceil(total_ms / ms_per_long)
    for i in range(total_longs):
        chunk = aligned_audio[int(i * ms_per_long) : int((i + 1) * ms_per_long)]
        if len(chunk) > 0 and not is_chunk_blank(chunk, args.thresh):
            filename = f"long_{str(i + 1).zfill(2)}.{file_ext}"
            rel_path = f"{folder_long}/{filename}"
            chunk.export(os.path.join(args.output_dir, folder_long, filename), format=file_ext)
            samples_long.append(rel_path)

    # 4. MASTER JSON STORAGE UPDATE
    master_data = {}
    if os.path.exists(args.json_path):
        try:
            with open(args.json_path, "r") as f:
                master_data = json.load(f)
        except json.JSONDecodeError:
            pass

    if "_base" not in master_data:
        master_data["_base"] = "http://localhost:5432/"
    if "_metadata" not in master_data:
        master_data["_metadata"] = {}

    master_data[folder_short] = samples_short
    master_data[folder_bar] = samples_bar
    master_data[folder_long] = samples_long

    master_data["_metadata"][base_name] = {
        "bpm": args.bpm,
        "key": args.key.strip().lower(),
        "beats_per_bar": args.beats,
        "source_url": args.url,
        "credit": args.credit
    }

    with open(args.json_path, "w") as f:
        json.dump(master_data, f, indent=2, sort_keys=True)

    # 5. WRITE MARKDOWN README COMPILATION DOCUMENTATION
    update_readme(args.output_dir, master_data["_metadata"])

    print(f"\nSuccessfully stored '{base_name}' in '{args.json_path}'!")

if __name__ == "__main__":
    process_cli()
