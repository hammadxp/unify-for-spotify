# Unify for Spotify

Unify keeps a local copy of your Spotify music library and syncs it against Spotify when you run it again.

It supports:

- Downloading a single track
- Downloading a single playlist
- Downloading your Liked Songs
- Moving already-downloaded local files into a playlist-named folder by matching them against a Spotify playlist

## What It Does

- Downloads audio stream from Spotify using your own account session
- Writes metadata such as title, album, artist, cover art, genres, and lyrics
- Renames conflicting files safely
- Removes duplicates from the local library
- Updates the file modified date to match the track's Spotify added date
- Lets you run fully interactively or provide CLI arguments for automation

## Important Notes

- Uploaded/local-only Spotify tracks are skipped because they cannot be fetched through the current download flow
- Extra files that do not match the Spotify source are safely removed during full-library syncs such as playlists and `liked_no_cache`
- Archive behavior is disabled by default
- Temporary downloads are stored in `~/Unify Downloads` by default unless you override that path
- This project is currently Windows-focused

## For End Users

If you are using the packaged `.exe`, you do not need to install Python.

### Before First Run

1. Download or place the `.exe` somewhere convenient.
2. Create a `.env` file using the sample from [`example_files/.env`](https://github.com/hammadxp/unify-for-spotify/blob/main/example_files/.env).
3. Fill in your Spotify API values:

```env
SPOTIFY_CLIENT_ID=""
SPOTIFY_CLIENT_SECRET=""
SPOTIFY_REDIRECT_URI="http://127.0.0.1:8888/callback"
```

4. Keep the `.env` file next to the `.exe`.
5. Optionally place a `config.json` next to the `.exe` if you want it to be picked up automatically.
6. Run the app once and complete the browser-based Spotify sign-in flow when prompted.

### Optional Config File

If `config.json` exists next to `unify.exe`, it is loaded automatically. You can also keep a config file anywhere on your PC and pass it with `--config-path`.

Example:

```json
{
  "option_type": "liked",
  "destination_folder": "C:\\Music\\Spotify",
  "region": "US",
  "download_format": "mp3",
  "download_quality": "high",
  "transcode_bitrate": "auto",
  "chunk_size": 20000,
  "retry_attempts": 0,
  "temp_download_folder": "C:\\Users\\{YourUserName}\\Unify Downloads",
  "set_file_mtime_from_added_at": false
}
```

### Default Behavior

If you do not provide a config file, the app uses these built-in defaults:

- `region`: `US`
- `download_format`: `mp3`
- `download_quality`: `high`
- `transcode_bitrate`: `auto`
- `chunk_size`: `20000`
- `retry_attempts`: `0`
- `temp_download_folder`: `%USERPROFILE%\\Unify Downloads`
- archive: disabled

If a config file is present, only the keys you explicitly set override these defaults. Missing keys continue using the built-in defaults.

Config files can also provide runtime choices that are normally passed as CLI arguments: `option_type`, `playlist_url`, `track_url`, `destination_folder`, `source_folder`, `enable_archive`, `archive_folder`, and `set_file_mtime_from_added_at`. Explicit CLI arguments always override matching config values.

### Running Interactively

Launch the app without arguments:

```powershell
unify.exe
```

The app will prompt you for the option type and any missing folders or Spotify URLs.

### Running With Arguments

Examples:

```powershell
unify.exe --option-type track --track-url "https://open.spotify.com/track/..." --destination-folder "C:\Music\Singles"
unify.exe --option-type playlist --playlist-url "https://open.spotify.com/playlist/..." --destination-folder "C:\Music\Playlists"
unify.exe --option-type playlist --playlist-url "https://open.spotify.com/playlist/..." --destination-folder "C:\Music\Spotify" --enable-archive --archive-folder "C:\Music\Unify Archive"
unify.exe --option-type liked --destination-folder "C:\Music\Spotify"
unify.exe --option-type liked_no_cache --destination-folder "C:\Music\Spotify"
unify.exe --option-type liked --destination-folder "C:\Music\Spotify" --temp-download-folder "C:\Temp\Unify"
unify.exe --option-type liked --destination-folder "C:\Music\Spotify" --config-path "C:\Configs\unify.json"
unify.exe --option-type liked --destination-folder "C:\Music\Spotify" --set-file-mtime-from-added-at
```

### CLI Options

- `--option-type`: `track`, `playlist`, `liked`, `liked_no_cache`, or `move_playlist_matches`
- `liked`: incremental Liked Songs sync; after the first full fetch for a destination folder, later runs only request newer liked tracks
- `liked_no_cache`: full Liked Songs library fetch every run
- `--track-url`: required for `track` mode unless you want to be prompted
- `--playlist-url`: used for `playlist` and `move_playlist_matches`
- `--destination-folder`: destination folder for downloads
- `--source-folder`: source folder for `move_playlist_matches`
- `--config-path`: optional path to a JSON config file
- `--region`: Spotify market code used when reading track/playlist data
- `--download-format`: `aac`, `fdk_aac`, `m4a`, `mp3`, `ogg`, `opus`, or `vorbis`
- `--download-quality`: `normal` or `high`
- `--transcode-bitrate`: bitrate preference for transcoded output
- `--chunk-size`: download chunk size in bytes
- `--retry-attempts`: retries for failed HTTP requests
- `--temp-download-folder`: optional temp working folder; defaults to `%USERPROFILE%\\Unify Downloads`
- `--enable-archive`: enables archiving for unmatched local files
- `--archive-folder`: required when `--enable-archive` is used
- `--set-file-mtime-from-added-at`: sets each downloaded file's modified time from Spotify's `added_at` timestamp

### Stored Files

- `.env`: Spotify API credentials
- `.cache-spotipy`: cached Spotify Web API token
- `credentials.json`: cached librespot login session
- `unify-state.json`: incremental liked-songs scan state keyed by destination folder

Delete `credentials.json` if you want to sign in with a different Spotify account.

## For Developers

### Requirements

- Python 3.10+
- `ffmpeg` available on your `PATH` if you want audio transcoding to work reliably
- A Spotify app/client for obtaining API credentials

### Setup

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies.
4. Create a `.env` file from [`example_files/.env`](https://github.com/hammadxp/unify-for-spotify/blob/main/example_files/.env).
5. Optionally copy or create a config JSON anywhere and pass it with `--config-path`, or keep `config.json` beside the app for automatic loading.

Commands:

```powershell
git clone https://github.com/hammadxp/unify-for-spotify
cd unify-for-spotify
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Example Developer Runs

```powershell
python main.py
python main.py --option-type playlist --playlist-url "https://open.spotify.com/playlist/..." --destination-folder "C:\Music\Spotify" --config-path ".\example_files\config.json"
python main.py --option-type liked --destination-folder "C:\Music\Spotify"
python main.py --option-type liked_no_cache --destination-folder "C:\Music\Spotify"
python main.py --option-type liked --destination-folder "C:\Music\Spotify" --enable-archive --archive-folder "C:\Music\Archive"
python main.py --option-type liked --destination-folder "C:\Music\Spotify" --set-file-mtime-from-added-at
```

### Packaging With PyInstaller

A basic one-file build looks like this:

```powershell
pyinstaller --onefile --name unify main.py
```

If you ship the `.exe`, make sure end users also have access to:

- `.env`
- `ffmpeg` if your build/runtime setup requires it
- any optional config JSON they want to use with `--config-path` or place beside the `.exe` as `config.json`

### Project Entry Point

- Main entry point: [`main.py`](https://github.com/hammadxp/unify-for-spotify/blob/main/main.py)
- Core app logic: [`unify.py`](https://github.com/hammadxp/unify-for-spotify/blob/main/unify.py)
- CLI definitions: [`cli_args.py`](https://github.com/hammadxp/unify-for-spotify/blob/main/cli_args.py)

## Troubleshooting

- If Spotify API auth fails, check the values in `.env`.
- If you run `unify.exe` directly from `cmd`, keep `.env`, `config.json`, `.cache-spotipy`, `credentials.json`, and `unify-state.json` beside the `.exe` if you want them shared by that build.
- If the browser login does not complete, verify `SPOTIFY_REDIRECT_URI`.
- If transcoding fails, install `ffmpeg` and make sure it is on your `PATH`.
- If a supplied config path fails, verify that the file exists and contains valid JSON.
- If archive mode is enabled, you must also provide `--archive-folder`.

## Sample Files

- Sample env: [`example_files/.env`](https://github.com/hammadxp/unify-for-spotify/blob/main/example_files/.env)
- Sample config: [`example_files/config.json`](https://github.com/hammadxp/unify-for-spotify/blob/main/example_files/config.json)

## Feedback

If something breaks or you want a feature, open an issue and include:

- the command you ran
- whether you used the `.exe` or Python
- whether you used `--config-path`
- the relevant error message

Built with love in Pakistan ❤️
