# random.scripts
collection of random scripts

## music.video.scrape.py
Scrapes metadata from [IMVDB](https://imvdb.com) and YouTube for local music video files, organizes them into `Artist/Artist - Song/` folder structure, creates Kodi-compatible NFO files, and optionally downloads higher quality versions from YouTube if available.

### Features
- Parses artist/song from filenames, uses metadata for final naming
- Falls back to YouTube search if IMVDB has no match
- Compares local vs YouTube quality, downloads upgrades (keeps original)
- Skips static image "videos" (low bitrate detection)
- Scrape entire artist or director filmographies via IMVDB slugs

### Usage
```bash
# Organize existing files
python mvorganizer.py -s /path/to/source -t /path/to/target

# Parse weirdly named scene files
python mvorganizer.py -s /path/to/source -t /path/to/target -o

# Scrape all videos by artist
python mvorganizer.py --artist nirvana -t /path/to/target

# Scrape all videos by director
python mvorganizer.py --director samuel-bayer -t /path/to/target

# Windows (yt-dlp in same directory)
python mvorganizer.py -s source -t target --win
```

### Requirements
- Python 3
- `requests`
- `yt-dlp`
- `ffprobe` (for quality comparison)
- IMVDB API key (set in script)
