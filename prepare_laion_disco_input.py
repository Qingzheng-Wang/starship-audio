#!/usr/bin/env python3
"""
Convert LAION-DISCO-12M parquet files to starship input format (JSON).
This script reads the parquet metadata and creates a JSON file suitable for starship server.
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
import pyarrow.parquet as pq
from tqdm import tqdm


def load_laion_disco_metadata(base_dir: str) -> pd.DataFrame:
    """
    Load all LAION-DISCO-12M parquet files.
    
    Args:
        base_dir: Base directory containing parquet files
        
    Returns:
        Combined DataFrame with all metadata
    """
    base_path = Path(base_dir)
    parquet_files = sorted(base_path.glob("**/*.parquet"))
    
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {base_dir}")
    
    print(f"Found {len(parquet_files)} parquet file(s)")
    
    # Load all parquet files
    dfs = []
    for pf in tqdm(parquet_files, desc="Loading parquet files"):
        df = pd.read_parquet(pf)
        dfs.append(df)
    
    # Combine all dataframes
    combined_df = pd.concat(dfs, ignore_index=True)
    print(f"Total records: {len(combined_df)}")
    
    return combined_df


def convert_to_starship_format(
    df: pd.DataFrame,
    output_path: str,
    chunk_size: int = None,
    start_idx: int = 0,
    end_idx: int = None,
) -> None:
    """
    Convert LAION-DISCO-12M DataFrame to starship input format.
    
    Args:
        df: DataFrame with LAION-DISCO-12M metadata
        output_path: Output JSON file path
        chunk_size: If specified, process only this many records
        start_idx: Start index for processing
        end_idx: End index for processing
    """
    
    # Determine slice
    if end_idx is None:
        end_idx = len(df)
    if chunk_size is not None:
        end_idx = min(start_idx + chunk_size, len(df))
    
    df_slice = df.iloc[start_idx:end_idx]
    
    print(f"Converting records {start_idx} to {end_idx} ({len(df_slice)} total)")
    
    # Convert to starship format
    starship_entries = []
    
    for idx, row in tqdm(df_slice.iterrows(), total=len(df_slice), desc="Converting"):
        # Get song_id and ensure it's a string
        song_id = str(row.get('song_id', '')).strip()
        
        if not song_id or song_id == 'nan':
            continue
        
        # Parse artist_names if it's a string (might be stored as string in parquet)
        artist_names = row.get('artist_names', [])
        if isinstance(artist_names, str):
            # Try to parse as list if it looks like a list string
            try:
                import ast
                artist_names = ast.literal_eval(artist_names)
            except:
                artist_names = [artist_names] if artist_names else []
        elif not isinstance(artist_names, list):
            artist_names = []
        
        # Parse artist_ids similarly
        artist_ids = row.get('artist_ids', [])
        if isinstance(artist_ids, str):
            try:
                import ast
                artist_ids = ast.literal_eval(artist_ids)
            except:
                artist_ids = [artist_ids] if artist_ids else []
        elif not isinstance(artist_ids, list):
            artist_ids = []
        
        # Create starship entry with proper type handling
        entry = {
            # Core fields for starship
            "song_id": song_id,
            "url": f"https://www.youtube.com/watch?v={song_id}",
            "output_path": f"{song_id[:2]}/{song_id}",  # Use 2-char prefix for subdirectory
            
            # LAION-DISCO-12M metadata
            "title": str(row.get('title', '')),
            "artist_names": artist_names,
            "artist_ids": artist_ids,
            "album_name": str(row.get('album_name', '')),
            "album_id": str(row.get('album_id', '')),
            "isExplicit": bool(row.get('isExplicit', False)),
            "views": str(row.get('views', '')),
            "duration": int(row.get('duration', 0)) if pd.notna(row.get('duration')) else 0,
            
            # yt-dlp options for audio-only with original format preservation
            "ytdl_opts": {
                "format": "bestaudio/best",
                "outtmpl": "./audiodata/%(id)s.%(ext)s",
                "writeinfojson": True,
                "writedescription": True,
                "quiet": True,
                "no_warnings": False,
                "postprocessors": [],  # No post-processing to preserve original format
                # Retry settings for robustness
                "socket_timeout": 30,
                "retries": 3,
                "fragment_retries": 3,
            }
        }
        
        starship_entries.append(entry)
    
    # Write to JSON file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(starship_entries, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Saved {len(starship_entries)} entries to {output_path}")
    print(f"   Sample entry:")
    if starship_entries:
        sample = starship_entries[0]
        print(f"   - Song ID: {sample['song_id']}")
        print(f"   - Title: {sample['title']}")
        print(f"   - Artists: {sample['artist_names']}")
        print(f"   - Duration: {sample['duration']}s")


def create_chunked_inputs(
    df: pd.DataFrame,
    output_dir: str,
    chunk_size: int = 10000,
) -> List[str]:
    """
    Create multiple chunked JSON files for parallel processing.
    
    Args:
        df: DataFrame with LAION-DISCO-12M metadata
        output_dir: Output directory for JSON files
        chunk_size: Number of records per chunk
        
    Returns:
        List of output file paths
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    total_records = len(df)
    num_chunks = (total_records + chunk_size - 1) // chunk_size
    
    print(f"Creating {num_chunks} chunks with ~{chunk_size} records each")
    
    output_files = []
    
    for chunk_idx in range(num_chunks):
        start_idx = chunk_idx * chunk_size
        end_idx = min(start_idx + chunk_size, total_records)
        
        output_file = output_path / f"laion_disco_chunk_{chunk_idx:06d}.json"
        
        convert_to_starship_format(
            df,
            str(output_file),
            start_idx=start_idx,
            end_idx=end_idx,
        )
        
        output_files.append(str(output_file))
    
    return output_files


def main():
    parser = argparse.ArgumentParser(
        description="Convert LAION-DISCO-12M parquet to starship JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert entire dataset to single JSON file
  python prepare_laion_disco_input.py \\
      --input /ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m \\
      --output laion_disco_all.json
  
  # Create chunked files for parallel processing
  python prepare_laion_disco_input.py \\
      --input /ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m \\
      --output-dir ./starship_inputs \\
      --chunked \\
      --chunk-size 10000
  
  # Process specific range
  python prepare_laion_disco_input.py \\
      --input /ocean/projects/cis210027p/shared/corpora/laion_laion_disco_12m \\
      --output laion_disco_subset.json \\
      --start 0 \\
      --end 50000
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input directory with LAION-DISCO-12M parquet files'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output JSON file path (for single file output)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Output directory for chunked files'
    )
    
    parser.add_argument(
        '--chunked',
        action='store_true',
        help='Create multiple chunked files instead of single file'
    )
    
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=10000,
        help='Number of records per chunk (default: 10000)'
    )
    
    parser.add_argument(
        '--start',
        type=int,
        default=0,
        help='Start index (for subset processing)'
    )
    
    parser.add_argument(
        '--end',
        type=int,
        default=None,
        help='End index (for subset processing)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.chunked and not args.output:
        parser.error("Either --output or --chunked (with --output-dir) must be specified")
    
    if args.chunked and not args.output_dir:
        parser.error("--output-dir must be specified when using --chunked")
    
    # Load metadata
    print("Loading LAION-DISCO-12M metadata...")
    df = load_laion_disco_metadata(args.input)
    
    # Convert
    if args.chunked:
        create_chunked_inputs(
            df,
            args.output_dir,
            chunk_size=args.chunk_size,
        )
    else:
        convert_to_starship_format(
            df,
            args.output,
            start_idx=args.start,
            end_idx=args.end,
        )
    
    print("\n✅ Conversion complete!")


if __name__ == "__main__":
    main()




