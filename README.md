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
- Can update the file modified date to match the track's Spotify added date
- Lets you run fully interactively or provide CLI arguments for automation

## Important Notes

- Uploaded/local-only Spotify tracks are skipped because they cannot be fetched through the current download flow
- Extra files that do not match the Spotify source are safely removed during full-library syncs such as playlists and `liked_full`
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

Configuration is layered in this order:

1. Built-in defaults
2. `config.json` beside the `.exe`, when present
3. The file passed with `--config-path`, when present
4. Explicit CLI arguments

Later layers override earlier layers, so a runtime config passed with `--config-path` overrides both built-in defaults and the adjacent `config.json`.

Example:

```json
{
  "option_type": "liked_full",
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
- `enable_archive`: `false`
- `archive_folder`: unset
- `set_file_mtime_from_added_at`: `false`

If one or more config files are present, only the keys you explicitly set override earlier values. Missing keys continue using the built-in defaults or values from earlier config layers. Config keys may be written as JSON-style names such as `destination_folder`, CLI-style names such as `destination-folder`, or full CLI flags such as `--destination-folder`.

Config files can also provide runtime choices that are normally passed as CLI arguments: `option_type`, `playlist_url`, `track_url`, `destination_folder`, `source_folder`, `enable_archive`, `archive_folder`, and `set_file_mtime_from_added_at`. Explicit CLI arguments always override matching config values.

For playlist mode, `playlist_url` may be a string, a whitespace-separated string, or an array of playlist URLs.

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
unify.exe --option-type playlist --playlist-url "https://open.spotify.com/playlist/..." "https://open.spotify.com/playlist/..." --destination-folder "C:\Music\Playlists"
unify.exe --option-type playlist --playlist-url "https://open.spotify.com/playlist/..." --destination-folder "C:\Music\Spotify" --enable-archive --archive-folder "C:\Music\Unify Archive"
unify.exe --option-type liked_full --destination-folder "C:\Music\Spotify"
unify.exe --option-type liked_partial --destination-folder "C:\Music\Spotify"
unify.exe --option-type liked_full --destination-folder "C:\Music\Spotify" --temp-download-folder "C:\Temp\Unify"
unify.exe --option-type liked_full --destination-folder "C:\Music\Spotify" --config-path "C:\Configs\unify.json"
unify.exe --option-type liked_full --destination-folder "C:\Music\Spotify" --set-file-mtime-from-added-at
```

### CLI Options

- `--option-type`: `track`, `playlist`, `liked_full`, `liked_partial`, or `move_playlist_matches`
- `--option-type liked_full`: full Liked Songs library fetch every run; this also refreshes the saved timestamp for later partial runs
- `--option-type liked_partial`: new-items-only Liked Songs sync using the saved timestamp for the destination folder
- `--track-url`: required for `track` mode unless you want to be prompted
- `--playlist-url`: used for `playlist` and `move_playlist_matches`; `playlist` mode accepts multiple URLs in one run
- `--destination-folder`: destination folder for downloads; when multiple playlist URLs are supplied, each playlist is synced into its own playlist-named folder inside this folder
- `--source-folder`: source folder for `move_playlist_matches`
- `--config-path`: optional path to a JSON config file
- `--region`: Spotify market code used when reading track/playlist data
- `--download-format`: `m4a`, `mp3`, `ogg`, or `opus`
- `--download-quality`: `normal` or `high`
- `--transcode-bitrate`: accepted for config compatibility; current output bitrate follows `--download-quality`
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
python main.py --option-type playlist --playlist-url "https://open.spotify.com/playlist/..." "https://open.spotify.com/playlist/..." --destination-folder "C:\Music\Spotify"
python main.py --option-type liked_full --destination-folder "C:\Music\Spotify"
python main.py --option-type liked_partial --destination-folder "C:\Music\Spotify"
python main.py --option-type liked_full --destination-folder "C:\Music\Spotify" --enable-archive --archive-folder "C:\Music\Archive"
python main.py --option-type liked_full --destination-folder "C:\Music\Spotify" --set-file-mtime-from-added-at
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
