#!/usr/bin/env python3
"""
Music Video Organizer
Scrapes metadata from IMVDB and YouTube, organizes files, optionally downloads better quality.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests

# Configuration
IMVDB_API_KEY = "YOUR_IMVDB_API_KEY"
IMVDB_BASE_URL = "https://imvdb.com/api/v1"
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.flv', '.wmv', '.m4v', '.mpg', '.mpeg', '.m2v'}


class IMVDBClient:
    """Client for IMVDB API"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "IMVDB-APP-KEY": api_key,
            "Accept": "application/json"
        }
    
    def search_videos(self, query):
        """Search for music videos"""
        url = f"{IMVDB_BASE_URL}/search/videos"
        params = {"q": query}
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json()
        return None
    
    def get_video_details(self, video_id):
        """Get full details for a video"""
        includes = "sources,credits,bts,countries,featured,popularity,aka"
        url = f"{IMVDB_BASE_URL}/video/{video_id}?include={includes}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return None
    
    def get_entity_videos(self, entity_slug):
        """Get all videos for an artist or director"""
        url = f"{IMVDB_BASE_URL}/entity/{entity_slug}/videos"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return None


class YTDLPClient:
    """Client for yt-dlp operations"""
    
    def __init__(self, windows_mode=False):
        self.ytdlp = ".\\yt-dlp" if windows_mode else "yt-dlp"
    
    def get_video_info(self, query_or_url):
        """Get video metadata from YouTube"""
        try:
            # If it's a YouTube ID, construct URL
            if re.match(r'^[a-zA-Z0-9_-]{11}$', query_or_url):
                query_or_url = f"https://www.youtube.com/watch?v={query_or_url}"
            # If it's a search query
            elif not query_or_url.startswith('http'):
                query_or_url = f"ytsearch1:{query_or_url}"
            
            result = subprocess.run(
                [self.ytdlp, '--dump-json', '--no-download', '--no-playlist', query_or_url],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            print(f"  yt-dlp error: {e}")
        return None
    
    def get_best_formats(self, youtube_id):
        """Get available formats for quality comparison"""
        try:
            url = f"https://www.youtube.com/watch?v={youtube_id}"
            result = subprocess.run(
                [self.ytdlp, '--dump-json', '--no-download', url],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                return {
                    'width': data.get('width'),
                    'height': data.get('height'),
                    'vcodec': data.get('vcodec'),
                    'acodec': data.get('acodec'),
                    'vbr': data.get('vbr'),
                    'abr': data.get('abr'),
                    'ext': data.get('ext'),
                    'filesize': data.get('filesize_approx') or data.get('filesize')
                }
        except Exception as e:
            print(f"  Format check error: {e}")
        return None
    
    def download_video(self, youtube_id, output_path):
        """Download best quality video"""
        try:
            url = f"https://www.youtube.com/watch?v={youtube_id}"
            result = subprocess.run(
                [
                    self.ytdlp,
                    '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    '-o', str(output_path),
                    url
                ],
                capture_output=True,
                text=True,
                timeout=600
            )
            return result.returncode == 0
        except Exception as e:
            print(f"  Download error: {e}")
        return False


def parse_filename(filename, oddities=False):
    """
    Parse artist and song title from filename.
    Handles formats:
      - Artist Name - Song Title (extra info).ext
      - Artist_Name_-_Song_Title_(extra_info).ext
    
    With oddities=True, also handles:
      - Artist-song_title-junk-junk
      - Artist.feat.Artist2.-.Song.Title.[stuff]
    """
    # Remove extension
    name = Path(filename).stem
    
    if oddities:
        # Strip common scene junk from end
        scene_junk = [
            r'[-\.]svcd.*$', r'[-\.]dvdrip.*$', r'[-\.]lbvidz.*$', r'[-\.]gnrules.*$',
            r'[-\.]littlec.*$', r'[-\.]mV$', r'[-\.]mb$', r'[-\.]fioretti.*$',
            r'[-\.]detox.*$', r'[-\.]tolerance.*$', r'[-\.]gray.*$', r'[-\.]fused.*$',
            r'[-\.]EViLSouL.*$', r'[-\.]sZb.*$', r'[-\.]X264.*$', r'[-\.]AC3.*$',
            r'\[.*?\]', r'\(Official Video\)', r'\(Official\)', r'"', r'＂'
        ]
        for pattern in scene_junk:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        # Replace dots with spaces (but not double dots - handle those first)
        name = name.replace('..', ' . ')
        name = name.replace('.', ' ')
        
        # Replace underscores with spaces
        name = name.replace('_', ' ')
        
        # Clean up multiple spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Try to split on ' - '
        if ' - ' in name:
            parts = name.split(' - ', 1)
            artist = parts[0].strip()
            song_part = parts[1].strip()
            
            # Remove parenthetical/bracketed info from song title for searching
            song_clean = re.sub(r'\s*[\(\[\{].*?[\)\]\}]\s*', '', song_part).strip()
            
            # Extract the parenthetical info
            parens = re.findall(r'[\(\[\{].*?[\)\]\}]', song_part)
            extra_info = ' '.join(parens) if parens else None
            
            return {
                'artist': artist,
                'song': song_clean,
                'song_original': song_part,
                'extra_info': extra_info
            }
        
        # Try " by " separator (e.g., "Artist by Song" or "Artist Featuring X by Song")
        if ' by ' in name.lower():
            idx = name.lower().index(' by ')
            before = name[:idx].strip()
            after = name[idx+4:].strip()
            
            # Remove "Featuring." or "feat." from artist
            artist = re.sub(r'\s+Featuring\.?\s+.*$', '', before, flags=re.IGNORECASE)
            song_part = after
            
            song_clean = re.sub(r'\s*[\(\[\{].*?[\)\]\}]\s*', '', song_part).strip()
            parens = re.findall(r'[\(\[\{].*?[\)\]\}]', song_part)
            extra_info = ' '.join(parens) if parens else None
            
            return {
                'artist': artist,
                'song': song_clean,
                'song_original': song_part,
                'extra_info': extra_info
            }
        
        # Fallback: try splitting on dash
        parts = re.split(r'\s*-\s*', name)
        if len(parts) >= 2:
            artist = parts[0].strip()
            # Take second part as song, ignore rest (scene junk)
            song_part = parts[1].strip()
            
            song_clean = re.sub(r'\s*[\(\[\{].*?[\)\]\}]\s*', '', song_part).strip()
            parens = re.findall(r'[\(\[\{].*?[\)\]\}]', song_part)
            extra_info = ' '.join(parens) if parens else None
            
            return {
                'artist': artist,
                'song': song_clean,
                'song_original': song_part,
                'extra_info': extra_info
            }
        
        return None
    
    # Standard parsing
    # Replace underscores with spaces
    name = name.replace('_', ' ')
    
    # Try to split on ' - '
    if ' - ' in name:
        parts = name.split(' - ', 1)
        artist = parts[0].strip()
        song_part = parts[1].strip()
        
        # Remove parenthetical/bracketed info from song title for searching
        # but keep original for reference
        song_clean = re.sub(r'\s*[\(\[\{].*?[\)\]\}]\s*', '', song_part).strip()
        
        # Extract the parenthetical info
        parens = re.findall(r'[\(\[\{].*?[\)\]\}]', song_part)
        extra_info = ' '.join(parens) if parens else None
        
        return {
            'artist': artist,
            'song': song_clean,
            'song_original': song_part,
            'extra_info': extra_info
        }
    
    return None


def get_local_video_info(filepath):
    """Get resolution/quality info from local file using ffprobe"""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', '-show_format', str(filepath)
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            video_stream = None
            audio_stream = None
            
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video' and not video_stream:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and not audio_stream:
                    audio_stream = stream
            
            return {
                'width': video_stream.get('width') if video_stream else None,
                'height': video_stream.get('height') if video_stream else None,
                'vcodec': video_stream.get('codec_name') if video_stream else None,
                'acodec': audio_stream.get('codec_name') if audio_stream else None,
                'duration': float(data.get('format', {}).get('duration', 0)),
                'filesize': int(data.get('format', {}).get('size', 0))
            }
    except Exception as e:
        print(f"  ffprobe error: {e}")
    return None


def is_youtube_better(local_info, yt_info):
    """Compare local file quality vs YouTube available quality"""
    if not local_info or not yt_info:
        return False
    
    # Check if YouTube video is likely a static image (very low video bitrate)
    yt_vbr = yt_info.get('vbr') or 0
    if yt_vbr < 100:  # Less than 100kbps video bitrate = probably static image
        return False
    
    local_height = local_info.get('height') or 0
    yt_height = yt_info.get('height') or 0
    
    # YouTube is better if resolution is significantly higher
    if yt_height > local_height + 100:  # At least 100px higher
        return True
    
    return False


def sanitize_filename(name):
    """Remove invalid characters from filename/dirname"""
    # Replace invalid chars with underscore
    invalid = r'<>:"/\|?*'
    for char in invalid:
        name = name.replace(char, '_')
    return name.strip().rstrip('.')


def get_primary_artist(artist_name):
    """Strip featuring artists from artist name for folder creation"""
    result = re.sub(r'\s+feat\.?\s+.*$', '', artist_name, flags=re.IGNORECASE)
    return result.strip()


def create_nfo(metadata, output_path):
    """Create Kodi-style NFO file"""
    nfo_content = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    nfo_content.append('<musicvideo>')
    
    # Basic info
    nfo_content.append(f'  <title>{metadata.get("song_title", "")}</title>')
    nfo_content.append(f'  <artist>{metadata.get("artist", "")}</artist>')
    nfo_content.append(f'  <year>{metadata.get("year", "")}</year>')
    
    # Director(s)
    for director in metadata.get('directors', []):
        nfo_content.append(f'  <director>{director}</director>')
    
    # Additional metadata
    if metadata.get('aspect_ratio'):
        nfo_content.append(f'  <aspectratio>{metadata["aspect_ratio"]}</aspectratio>')
    
    if metadata.get('youtube_id'):
        nfo_content.append(f'  <youtube_id>{metadata["youtube_id"]}</youtube_id>')
    
    if metadata.get('imvdb_url'):
        nfo_content.append(f'  <imvdb_url>{metadata["imvdb_url"]}</imvdb_url>')
    
    if metadata.get('imvdb_id'):
        nfo_content.append(f'  <imvdb_id>{metadata["imvdb_id"]}</imvdb_id>')
    
    # View count
    if metadata.get('views'):
        nfo_content.append(f'  <views>{metadata["views"]}</views>')
    
    # Thumbnail
    if metadata.get('thumbnail'):
        nfo_content.append(f'  <thumb>{metadata["thumbnail"]}</thumb>')
    
    # Credits
    if metadata.get('credits'):
        nfo_content.append('  <credits>')
        for credit in metadata['credits']:
            nfo_content.append(f'    <credit role="{credit["role"]}">{credit["name"]}</credit>')
        nfo_content.append('  </credits>')
    
    nfo_content.append('</musicvideo>')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(nfo_content))


def find_best_match(imvdb_results, parsed_filename):
    """Find the best matching video from IMVDB results"""
    if not imvdb_results or not imvdb_results.get('results'):
        return None
    
    artist_lower = parsed_filename['artist'].lower()
    song_lower = parsed_filename['song'].lower()
    
    for result in imvdb_results['results']:
        # Handle potential bad data from API
        try:
            artists = result.get('artists')
            if not artists or not isinstance(artists, list) or len(artists) == 0:
                continue
            if not isinstance(artists[0], dict):
                continue
            result_artist = artists[0].get('name', '')
            if not isinstance(result_artist, str):
                continue
            result_artist = result_artist.lower()
        except (KeyError, TypeError, AttributeError):
            continue
        
        result_song = str(result.get('song_title', '')).lower()
        
        # Check for reasonable match
        if artist_lower in result_artist or result_artist in artist_lower:
            if song_lower in result_song or result_song in song_lower:
                return result
    
    return None


def process_file(filepath, target_dir, imvdb, ytdlp, debug=False, oddities=False):
    """Process a single video file"""
    filename = filepath.name
    print(f"\nProcessing: {filename}")
    
    # Parse filename
    parsed = parse_filename(filename, oddities=oddities)
    if not parsed:
        print(f"  Could not parse filename, skipping")
        return False
    
    print(f"  Artist: {parsed['artist']}")
    print(f"  Song: {parsed['song']}")
    
    # Search IMVDB
    search_query = f"{parsed['artist']} {parsed['song']}"
    if debug:
        print(f"  [DEBUG] IMVDB search query: {search_query}")
    
    imvdb_results = imvdb.search_videos(search_query)
    
    if debug and imvdb_results:
        print(f"  [DEBUG] IMVDB returned {imvdb_results.get('total_results', 0)} results")
    
    # Find best match
    match = find_best_match(imvdb_results, parsed)
    
    metadata = {
        'artist': parsed['artist'],
        'song_title': parsed['song'],
        'song_original': parsed['song_original'],
        'extra_info': parsed['extra_info'],
        'directors': [],
        'credits': [],
        'year': None,
        'youtube_id': None,
        'imvdb_url': None,
        'imvdb_id': None,
        'aspect_ratio': None,
        'thumbnail': None,
        'views': None
    }
    
    if match:
        print(f"  IMVDB match: {match['artists'][0]['name']} - {match['song_title']}")
        
        # Use IMVDB metadata for naming
        metadata['artist'] = match['artists'][0]['name']
        metadata['song_title'] = match['song_title']
        
        # Get full details
        details = imvdb.get_video_details(match['id'])
        if debug:
            print(f"  [DEBUG] IMVDB video ID: {match['id']}")
            if details:
                print(f"  [DEBUG] Got details, sources: {len(details.get('sources', []))}")
        
        if details:
            metadata['year'] = details.get('year')
            metadata['aspect_ratio'] = details.get('aspect_ratio')
            metadata['imvdb_url'] = details.get('url')
            metadata['imvdb_id'] = details.get('id')
            
            # Get thumbnail
            if details.get('image'):
                metadata['thumbnail'] = details['image'].get('o')  # Original size
            
            # Get directors
            for director in details.get('directors', []):
                metadata['directors'].append(director['entity_name'])
            
            # Get credits
            if details.get('credits'):
                for crew in details['credits'].get('crew', []):
                    metadata['credits'].append({
                        'role': crew['position_name'],
                        'name': crew['entity_name']
                    })
            
            # Get YouTube source
            for source in details.get('sources', []):
                if source.get('source') == 'youtube' and source.get('is_primary'):
                    metadata['youtube_id'] = source['source_data']
                    break
            
            # Get popularity
            if details.get('popularity'):
                metadata['views'] = details['popularity'].get('views_all_time')
    else:
        print(f"  No IMVDB match found")
    
    # If no YouTube ID from IMVDB, search YouTube directly
    if not metadata['youtube_id']:
        print(f"  Searching YouTube...")
        yt_info = ytdlp.get_video_info(search_query)
        if yt_info:
            metadata['youtube_id'] = yt_info.get('id')
            # Use YouTube metadata for naming if no IMVDB match
            if not match:
                if yt_info.get('artist'):
                    metadata['artist'] = yt_info['artist']
                if yt_info.get('track'):
                    metadata['song_title'] = yt_info['track']
            # Fill in missing year from YouTube
            if not metadata['year'] and yt_info.get('upload_date'):
                metadata['year'] = yt_info['upload_date'][:4]
            print(f"  Found YouTube: {metadata['youtube_id']}")
    
    # If no match anywhere, skip the file
    if not match and not metadata['youtube_id']:
        print(f"  No match found on IMVDB or YouTube, skipping")
        return False
    
    # Check if YouTube has better quality
    should_download = False
    if metadata['youtube_id']:
        local_info = get_local_video_info(filepath)
        yt_formats = ytdlp.get_best_formats(metadata['youtube_id'])
        
        if debug:
            print(f"  [DEBUG] Local info: {local_info}")
            print(f"  [DEBUG] YouTube formats: {yt_formats}")
        
        if local_info and yt_formats:
            print(f"  Local: {local_info.get('width')}x{local_info.get('height')} {local_info.get('vcodec')}")
            print(f"  YouTube: {yt_formats.get('width')}x{yt_formats.get('height')} {yt_formats.get('vcodec')} vbr:{yt_formats.get('vbr')}kbps")
            
            yt_vbr = yt_formats.get('vbr') or 0
            if yt_vbr < 100:
                print(f"  YouTube video bitrate too low ({yt_vbr}kbps), likely static image - skipping download")
            elif is_youtube_better(local_info, yt_formats):
                print(f"  YouTube has better quality")
                should_download = True
            else:
                print(f"  Local quality is same or better, skipping download")
                print(f"  YouTube has better quality")
                should_download = True
    
    # Create target directory structure
    primary_artist = get_primary_artist(metadata['artist'])
    artist_dir = sanitize_filename(primary_artist)
    video_dir = sanitize_filename(f"{metadata['artist']} - {metadata['song_title']}")
    target_path = Path(target_dir) / artist_dir / video_dir
    target_path.mkdir(parents=True, exist_ok=True)
    
    # Determine final filename
    original_ext = filepath.suffix
    is_already_original = '(original)' in filepath.stem.lower()
    
    if is_already_original:
        # Keep the filename as-is
        final_filename = filepath.name
    elif parsed['extra_info']:
        final_filename = f"{metadata['artist']} - {metadata['song_title']} {parsed['extra_info']}{original_ext}"
    else:
        final_filename = f"{metadata['artist']} - {metadata['song_title']}{original_ext}"
    final_filename = sanitize_filename(final_filename)
    
    # Download better quality if available
    if should_download and metadata['youtube_id'] and not is_already_original:
        print(f"  Downloading from YouTube...")
        download_filename = f"{metadata['artist']} - {metadata['song_title']}.mp4"
        download_filename = sanitize_filename(download_filename)
        download_path = target_path / download_filename
        
        if ytdlp.download_video(metadata['youtube_id'], download_path):
            print(f"  Downloaded successfully")
            # Move original with (original) suffix
            original_stem = filepath.stem
            original_new_name = f"{original_stem} (original){original_ext}"
            original_new_name = sanitize_filename(original_new_name)
            shutil.move(filepath, target_path / original_new_name)
            print(f"  Original preserved as: {original_new_name}")
        else:
            print(f"  Download failed, using original")
            shutil.move(filepath, target_path / final_filename)
    else:
        # Just move the original
        shutil.move(filepath, target_path / final_filename)
        print(f"  Moved to: {target_path / final_filename}")
    
    # Create NFO file
    nfo_path = target_path / "video.nfo"
    create_nfo(metadata, nfo_path)
    print(f"  Created NFO: {nfo_path}")
    
    return True


def process_directory(source_dir, target_dir, imvdb, ytdlp, debug=False, oddities=False):
    """Recursively process all video files in source directory"""
    processed = 0
    failed = 0
    
    for root, dirs, files in os.walk(source_dir):
        for filename in files:
            filepath = Path(root) / filename
            if filepath.suffix.lower() in VIDEO_EXTENSIONS:
                try:
                    if process_file(filepath, target_dir, imvdb, ytdlp, debug=debug, oddities=oddities):
                        processed += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"  Error processing {filepath}: {e}")
                    if debug:
                        import traceback
                        traceback.print_exc()
                    failed += 1
    
    print(f"\n{'='*50}")
    print(f"Processed: {processed}")
    print(f"Failed: {failed}")


def scrape_artist(artist_slug, target_dir, imvdb, ytdlp):
    """Download all videos by an artist"""
    print(f"Fetching videos for artist: {artist_slug}")
    
    videos = imvdb.get_entity_videos(artist_slug)
    if not videos:
        print(f"No videos found for artist: {artist_slug}")
        return
    
    results = videos.get('results', [])
    print(f"Found {len(results)} videos")
    
    for video in results:
        print(f"\n  {video['song_title']}")
        details = imvdb.get_video_details(video['id'])
        
        if details:
            youtube_id = None
            for source in details.get('sources', []):
                if source.get('source') == 'youtube':
                    youtube_id = source['source_data']
                    break
            
            if youtube_id:
                artist_name = details['artists'][0]['name'] if details.get('artists') else artist_slug
                song_title = details['song_title']
                
                artist_dir = sanitize_filename(artist_name)
                video_dir = sanitize_filename(f"{artist_name} - {song_title}")
                target_path = Path(target_dir) / artist_dir / video_dir
                target_path.mkdir(parents=True, exist_ok=True)
                
                download_filename = f"{artist_name} - {song_title}.mp4"
                download_filename = sanitize_filename(download_filename)
                download_path = target_path / download_filename
                
                if download_path.exists():
                    print(f"    Already exists, skipping")
                    continue
                
                print(f"    Downloading...")
                if ytdlp.download_video(youtube_id, download_path):
                    # Create metadata
                    metadata = {
                        'artist': artist_name,
                        'song_title': song_title,
                        'year': details.get('year'),
                        'directors': [d['entity_name'] for d in details.get('directors', [])],
                        'credits': [{'role': c['position_name'], 'name': c['entity_name']} 
                                   for c in details.get('credits', {}).get('crew', [])],
                        'youtube_id': youtube_id,
                        'imvdb_url': details.get('url'),
                        'imvdb_id': details.get('id'),
                        'aspect_ratio': details.get('aspect_ratio'),
                        'thumbnail': details.get('image', {}).get('o'),
                        'views': details.get('popularity', {}).get('views_all_time')
                    }
                    
                    create_nfo(metadata, target_path / "video.nfo")
                    print(f"    Done")
                else:
                    print(f"    Download failed")
            else:
                print(f"    No YouTube source")


def scrape_director(director_slug, target_dir, imvdb, ytdlp):
    """Download all videos by a director"""
    print(f"Fetching videos for director: {director_slug}")
    
    videos = imvdb.get_entity_videos(director_slug)
    if not videos:
        print(f"No videos found for director: {director_slug}")
        return
    
    results = videos.get('results', [])
    print(f"Found {len(results)} videos")
    
    for video in results:
        artist_name = video['artists'][0]['name'] if video.get('artists') else 'Unknown'
        print(f"\n  {artist_name} - {video['song_title']}")
        
        details = imvdb.get_video_details(video['id'])
        
        if details:
            youtube_id = None
            for source in details.get('sources', []):
                if source.get('source') == 'youtube':
                    youtube_id = source['source_data']
                    break
            
            if youtube_id:
                artist_dir = sanitize_filename(artist_name)
                video_dir = sanitize_filename(f"{artist_name} - {video['song_title']}")
                target_path = Path(target_dir) / artist_dir / video_dir
                target_path.mkdir(parents=True, exist_ok=True)
                
                download_filename = f"{artist_name} - {video['song_title']}.mp4"
                download_filename = sanitize_filename(download_filename)
                download_path = target_path / download_filename
                
                if download_path.exists():
                    print(f"    Already exists, skipping")
                    continue
                
                print(f"    Downloading...")
                if ytdlp.download_video(youtube_id, download_path):
                    metadata = {
                        'artist': artist_name,
                        'song_title': video['song_title'],
                        'year': details.get('year'),
                        'directors': [d['entity_name'] for d in details.get('directors', [])],
                        'credits': [{'role': c['position_name'], 'name': c['entity_name']} 
                                   for c in details.get('credits', {}).get('crew', [])],
                        'youtube_id': youtube_id,
                        'imvdb_url': details.get('url'),
                        'imvdb_id': details.get('id'),
                        'aspect_ratio': details.get('aspect_ratio'),
                        'thumbnail': details.get('image', {}).get('o'),
                        'views': details.get('popularity', {}).get('views_all_time')
                    }
                    
                    create_nfo(metadata, target_path / "video.nfo")
                    print(f"    Done")
                else:
                    print(f"    Download failed")
            else:
                print(f"    No YouTube source")


def main():
    parser = argparse.ArgumentParser(description='Music Video Organizer')
    parser.add_argument('-s', '--source', help='Source directory containing video files')
    parser.add_argument('-t', '--target', required=True, help='Target directory for organized files')
    parser.add_argument('-o', '--oddities', action='store_true', help='Parse oddly formatted filenames (dots, scene junk)')
    parser.add_argument('--artist', help='Scrape all videos by artist (use IMVDB slug)')
    parser.add_argument('--director', help='Scrape all videos by director (use IMVDB slug)')
    parser.add_argument('--win', action='store_true', help='Windows mode (use .\\yt-dlp)')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug output')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.source and not args.artist and not args.director:
        parser.error("Must specify --source, --artist, or --director")
    
    if args.debug:
        print("[DEBUG] Debug mode enabled")
        print(f"[DEBUG] Source: {args.source}")
        print(f"[DEBUG] Target: {args.target}")
        print(f"[DEBUG] Windows mode: {args.win}")
    
    # Initialize clients
    imvdb = IMVDBClient(IMVDB_API_KEY)
    ytdlp = YTDLPClient(windows_mode=args.win)
    
    if IMVDB_API_KEY == "YOUR_IMVDB_API_KEY":
        print("WARNING: IMVDB API key not set. Only YouTube lookups will work.")
    
    # Create target directory
    Path(args.target).mkdir(parents=True, exist_ok=True)
    
    # Run appropriate mode
    if args.artist:
        scrape_artist(args.artist, args.target, imvdb, ytdlp)
    elif args.director:
        scrape_director(args.director, args.target, imvdb, ytdlp)
    elif args.source:
        process_directory(args.source, args.target, imvdb, ytdlp, debug=args.debug, oddities=args.oddities)


if __name__ == "__main__":
    main()
