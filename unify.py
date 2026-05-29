# Built-in
import os
import re
import json
import math
import sys
import time
import ctypes
import platform
import unicodedata
import shutil
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tkinter import Tk, filedialog

# 3rd-party
import ffmpy
import music_tag
import mutagen.id3
import requests
import spotipy

from dotenv import load_dotenv
from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from send2trash import send2trash
from spotipy import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    BarColumn,
    TimeElapsedColumn,
    TextColumn,
    SpinnerColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn
)

VALID_DOWNLOAD_FORMATS = frozenset({"mp3", "m4a", "ogg", "opus"})
LEGACY_DOWNLOAD_FORMAT_ALIASES = {
    "aac": "m4a",
    "fdk_aac": "m4a",
    "vorbis": "ogg",
}


def normalize_download_format(value):
    if value is None:
        return None

    key = str(value).lower().strip()
    key = LEGACY_DOWNLOAD_FORMAT_ALIASES.get(key, key)

    return key if key in VALID_DOWNLOAD_FORMATS else None


def read_interactive_menu_key():
    """Return 'up', 'down', 'enter', or None for an unsupported key."""
    if platform.system() == "Windows":
        import msvcrt

        key = msvcrt.getwch()
        if key in ("\r", "\n"):
            return "enter"
        if key in ("\x00", "\xe0"):
            direction = msvcrt.getwch()
            if direction == "H":
                return "up"
            if direction == "P":
                return "down"
        return None

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    if ch in ("\n", "\r"):
        return "enter"
    if ch == "\x1b[A":
        return "up"
    if ch == "\x1b[B":
        return "down"
    return None


class Unify:
    def __init__(self):
        self.init_state()

    def get_runtime_base_folder(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))

    def get_runtime_file_path(self, *parts):
        return os.path.join(self.get_runtime_base_folder(), *parts)

    def get_default_temp_download_folder(self):
        return os.path.join(str(Path.home()), "Unify Downloads")

    def get_default_config(self):
        return {
            "region": "US",
            "download_format": "mp3",
            "download_quality": "high",
            "transcode_bitrate": "auto",
            "chunk_size": 20000,
            "retry_attempts": 0,
            "archive_folder": None,
            "temp_download_folder": self.get_default_temp_download_folder(),
        }

    def init_state(self):
        self.runtime_base_folder = self.get_runtime_base_folder()
        self.config = self.get_default_config()
        self.archive_enabled = False

        # Sync info
        self.option_type = ''
        self.playlist_url = ''
        self.playlist_id = ''
        self.track_url = ''
        self.track_id = ''
        self.playlist_name = 'Liked Songs'
        self.local_playlist_folder = ''
        self.source_folder = ''

        # Spotify tracks
        self.spotify_tracks_raw = []
        self.spotify_tracks_already_downloaded = []
        self.spotify_tracks_incomplete = []
        self.spotify_tracks_duplicate = []
        self.spotify_tracks_uploaded = []
        self.spotify_tracks_unavailable = []
        self.spotify_tracks_deleted = []
        self.spotify_tracks_to_download = []

        # Local tracks
        self.local_tracks_raw = []
        self.local_tracks_already_downloaded = []
        self.local_tracks_duplicate = []
        self.local_tracks_uploaded = []
        self.local_tracks_unmatched = []

        # Track IDs
        self.spotify_track_ids = set()
        self.local_track_ids = set()

        # Download handler
        self.temp_download_file = ''
        self.temp_transcode_file = ''
        self.final_output_file = ''
        self.currently_downloading_track = {}
        self.newly_downloaded_track = {}
        self.newly_downloaded_track_genres = ''
        self.newly_downloaded_track_lyrics = ''

        # Progress
        self.completed_index = 0
        self.progress_bar_text = ''

        # Other
        self.set_file_mtime_from_added_at = False
        self.did_partial_library_scan = False
        self.liked_tracks_cache_state = {}
        self.current_liked_tracks_cache_key = None
        self.current_liked_tracks_latest_added_at = None

    def show_status(self, message):
        if hasattr(self, 'status_bar') and hasattr(self, 'status_bar_id'):
            self.status_bar.update(
                self.status_bar_id, description=message, visible=True)
        else:
            print(f"\n{message}\n")

    def create_spotipy_session(self, verbose=True):
        try:
            load_dotenv(self.get_runtime_file_path(".env"))

            client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
            redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()

            if not client_id or not client_secret:
                raise ValueError(
                    "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env for Spotify Web API access")

            scope = "user-library-read playlist-read-private playlist-read-collaborative"
            self.spotipy_auth_manager = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=scope,
                cache_path=self.get_runtime_file_path(".cache-spotipy"),
                open_browser=True
            )

            self.spotipy_session = spotipy.Spotify(auth_manager=self.spotipy_auth_manager)
            self.ensure_spotipy_token()

            if verbose:
                print("spotipy user session activated.")

        except Exception as e:
            self.show_status(
                f"ERROR: Could not create Spotipy user session. ({e})")
            raise

    def ensure_spotipy_token(self, force_refresh=False):
        token_info = self.spotipy_auth_manager.get_cached_token()

        if force_refresh:
            if token_info and token_info.get('refresh_token'):
                self.spotipy_auth_manager.refresh_access_token(
                    token_info['refresh_token'])
            else:
                self.spotipy_auth_manager.get_access_token(as_dict=False)
            return

        validated_token = self.spotipy_auth_manager.validate_token(token_info)
        if not validated_token:
            self.spotipy_auth_manager.get_access_token(as_dict=False)

    def call_spotipy(self, method_name, *args, retry_count=0, **kwargs):
        try:
            self.ensure_spotipy_token()
            method = getattr(self.spotipy_session, method_name)
            return method(*args, **kwargs)

        except SpotifyException as e:
            if e.http_status == 401 and retry_count < 1:
                # Recover by rebuilding the client/auth manager once, since the
                # in-memory session can get out of sync with the cached token.
                self.create_spotipy_session(verbose=False)
                self.ensure_spotipy_token(force_refresh=True)
                return self.call_spotipy(method_name, *args, retry_count=retry_count + 1, **kwargs)

            if e.http_status == 429 and retry_count < 3:
                retry_after = 5
                headers = getattr(e, 'headers', {}) or {}
                if 'Retry-After' in headers:
                    try:
                        retry_after = max(1, int(float(headers['Retry-After'])))
                    except ValueError:
                        retry_after = 5
                self.show_status(
                    f"Spotify rate limited request to '{method_name}'. Retrying in {retry_after}s.")
                time.sleep(retry_after)
                return self.call_spotipy(method_name, *args, retry_count=retry_count + 1, **kwargs)

            raise

    def login_to_librespot(self):
        # check if the user has already logged in to librespot with their Spotify credentials, if so, retrieve session details from that file
        stored_credentials_path = self.get_runtime_file_path("credentials.json")
        session_config = Session.Configuration.Builder().set_stored_credential_file(
            stored_credentials_path
        ).build()

        if os.path.isfile(stored_credentials_path):
            try:
                self.librespot_session = Session.Builder(session_config).stored_file(stored_credentials_path).create()
                print("librespot user session activated.")
                return
            except Exception:
                pass

        # if user hasn't logged in to librespot before, sign them in
        try:
            def auth_url_callback(auth_url):
                print(f"\nOpening browser for librespot login: {auth_url}")
                try:
                    webbrowser.open(auth_url)
                except Exception:
                    pass

            print("librespot user session created.")
            self.librespot_session = Session.Builder(session_config).oauth(auth_url_callback).create()
            return

        except Exception as e:
            self.show_status(
                f"ERROR: Could not log in to librespot with OAuth. ({e})")
            raise

    def load_config(self, config_path=None):
        self.config = self.get_default_config()

        if not config_path:
            default_config_path = self.get_runtime_file_path("config.json")
            if os.path.isfile(default_config_path):
                config_path = default_config_path

        if not config_path:
            print("Using built-in default configuration.")
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as config_file:
                loaded_config = json.load(config_file)

            if not isinstance(loaded_config, dict):
                raise ValueError("Config file must contain a JSON object.")

            for key, value in loaded_config.items():
                if key in self.config and value is not None:
                    self.config[key] = value

            normalized_format = normalize_download_format(
                self.config.get("download_format"))
            if normalized_format:
                if str(self.config.get("download_format", "")).lower().strip() not in VALID_DOWNLOAD_FORMATS:
                    print(
                        f"Note: config download_format was mapped to '{normalized_format}' (supported: {', '.join(sorted(VALID_DOWNLOAD_FORMATS))}).")
                self.config["download_format"] = normalized_format
            else:
                print(
                    f"Warning: invalid download_format in config; using 'mp3'.")
                self.config["download_format"] = "mp3"

            for path_key in ("temp_download_folder", "archive_folder"):
                if self.config.get(path_key):
                    self.config[path_key] = os.path.abspath(
                        os.path.expanduser(self.config[path_key]))

            self.config["archive_folder"] = None
            print(f"Config loaded from: {config_path}")

        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Config file not found: {config_path}") from exc

    def get_state_file_path(self):
        return self.get_runtime_file_path("unify-state.json")

    def load_state(self):
        state_path = self.get_state_file_path()

        if not os.path.isfile(state_path):
            self.liked_tracks_cache_state = {}
            return

        try:
            with open(state_path, "r", encoding="utf-8") as state_file:
                loaded_state = json.load(state_file)

            liked_state = loaded_state.get("liked_tracks_last_scan", {})
            self.liked_tracks_cache_state = liked_state if isinstance(liked_state, dict) else {}
        except Exception:
            self.liked_tracks_cache_state = {}

    def save_state(self):
        state_path = self.get_state_file_path()
        payload = {
            "liked_tracks_last_scan": self.liked_tracks_cache_state
        }

        with open(state_path, "w", encoding="utf-8") as state_file:
            json.dump(payload, state_file, indent=2)

    def get_liked_tracks_cache_key(self):
        destination = os.path.abspath(self.local_playlist_folder or "")
        return destination.lower()

    def get_last_liked_tracks_scan_timestamp(self):
        if not self.current_liked_tracks_cache_key:
            return None

        raw_timestamp = self.liked_tracks_cache_state.get(self.current_liked_tracks_cache_key)
        if not raw_timestamp:
            return None

        try:
            datetime.strptime(raw_timestamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None

        return raw_timestamp

    def remember_liked_tracks_scan_timestamp(self):
        if self.option_type != "liked":
            return

        if not self.current_liked_tracks_cache_key or not self.current_liked_tracks_latest_added_at:
            return

        self.liked_tracks_cache_state[self.current_liked_tracks_cache_key] = self.current_liked_tracks_latest_added_at
        self.save_state()

    def prepare_runtime_state(self):
        self.load_state()

        if self.option_type == "liked":
            self.current_liked_tracks_cache_key = self.get_liked_tracks_cache_key()
        else:
            self.current_liked_tracks_cache_key = None

    def init_progress_bars(self):
        # CREATE PROGRESS BARS
        self.status_bar = Progress(TextColumn("{task.description}"))
        self.status_bar_id = self.status_bar.add_task("", visible=False)

        self.song_progress = Progress(TextColumn("{task.description}"))

        self.download_progress = Progress(
            TextColumn("[bold]{task.description}: {task.percentage:.0f}%"),
            BarColumn(),
            DownloadColumn(),
            TextColumn("|"),
            TransferSpeedColumn(),
            TextColumn("|"),
            TimeRemainingColumn(),
        )

        self.metadata_progress = Progress(
            TextColumn("[bold]{task.description}"),
            SpinnerColumn()
        )

        self.playlist_progress = Progress(
            TextColumn("{task.description}"),
            TimeElapsedColumn()
        )

        self.playlist_completed = Progress(TextColumn("{task.description}"))

        # INITIALIZE PLAYLIST PROGRESS
        self.playlist_progress_id = self.playlist_progress.add_task("")
        self.playlist_completed_id = self.playlist_completed.add_task(
            "", visible=False)

        # One row each: re-used every track so the live view does not grow without bound
        self.song_progress_id = self.song_progress.add_task("Preparing…")
        self.download_progress_id = self.download_progress.add_task("", total=None, visible=False)
        self.metadata_progress_id = self.metadata_progress.add_task("", visible=False)

        # PROGRESS PANEL (status_bar last so messages stay at the bottom of the live view)
        self.progress_panel = Panel(
            Group(
                Panel(Group(self.song_progress, self.download_progress, self.metadata_progress)),
                Panel(Group(self.playlist_progress, self.playlist_completed)),
                self.status_bar,
            )
        )

        self.progress_panel_alt = Panel(
            Group(
                self.playlist_completed,
                self.status_bar,
            )
        )

    ######################################################

    def prompt_option_selection(self):
        options = [
            {
                "value": "track",
                "label": "Download a single track",
            },
            {
                "value": "playlist",
                "label": "Download an individual playlist",
            },
            {
                "value": "liked",
                "label": "Download your Liked Songs library (new items only)",
            },
            {
                "value": "liked_no_cache",
                "label": "Download your Liked Songs library (No cache)",
            },
            {
                "value": "move_playlist_matches",
                "label": "Move unorganized downloaded songs to a playlist folder",
            },
        ]

        selected_index = 0

        while True:
            self.clear()
            self.splash()
            print("Use the Up/Down arrow keys and press Enter.\n")

            for index, option in enumerate(options):
                prefix = ">" if index == selected_index else " "
                print(f"{prefix} {option['label']}")

            key = read_interactive_menu_key()

            if key == "enter":
                chosen_option = options[selected_index]
                self.option_type = chosen_option["value"]

                if self.option_type == "liked":
                    self.playlist_name = "Liked Songs"
                elif self.option_type == "liked_no_cache":
                    self.playlist_name = "Liked Songs (No Cache)"

                print()
                return

            if key == "up":
                selected_index = (selected_index - 1) % len(options)
            elif key == "down":
                selected_index = (selected_index + 1) % len(options)

    def prompt_track_url(self):
        while True:
            track_url = input("Paste the Spotify song URL: ").strip()
            if track_url:
                self.track_url = track_url
                self.get_track_id()
                if self.track_id:
                    return

            print("\nPlease provide a valid Spotify song URL.\n")

    def prompt_playlist_url(self):
        while True:
            playlist_url = input("Paste the Spotify playlist URL: ").strip()
            if playlist_url:
                self.playlist_url = playlist_url
                self.get_playlist_id()
                if self.playlist_id:
                    return

            print("\nPlease provide a valid Spotify playlist URL.\n")

    def prompt_folder_selection(self, title):
        while True:
            folder = self.select_folder(title)
            if folder:
                return os.path.abspath(folder)

            print("\nA folder selection is required.\n")

    def prompt_destination_folder(self):
        self.local_playlist_folder = self.prompt_folder_selection(
            "Select the destination folder")

    def prompt_source_folder(self):
        self.source_folder = self.prompt_folder_selection(
            "Select the source folder")

    def select_folder(self, title):
        root = Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        try:
            return filedialog.askdirectory(title=title, mustexist=True)
        finally:
            root.destroy()

    def get_playlist_id(self):
        try:
            if match := re.match(r"https://open\.spotify\.com/playlist/([^?]+)", self.playlist_url):
                self.playlist_id = match.groups()[0]
            else:
                raise ValueError()

        except ValueError as e:
            self.playlist_id = ''
            self.show_status(
                f"ERROR: Bad playlist URL format. ({self.playlist_url})")

    def get_track_id(self):
        try:
            if match := re.match(r"https://open\.spotify\.com/track/([^?]+)", self.track_url):
                self.track_id = match.groups()[0]
            else:
                raise ValueError()

        except ValueError:
            self.track_id = ''
            self.show_status(
                f"ERROR: Bad track URL format. ({self.track_url})")

    def get_playlist_name(self):
        try:
            response = self.call_spotipy(
                'playlist', self.playlist_id, fields="name")
            self.playlist_name = response['name']

        except Exception as e:
            self.playlist_name = f"Playlist {self.playlist_id}"
            self.show_status(
                f"ERROR: Could not retrieve playlist name. ({e})")

    def get_track_name(self):
        try:
            response = self.call_spotipy('track', self.track_id, market=self.config['region'])
            title = response['name']
            artist = ", ".join([artist['name'] for artist in response['artists']])
            self.playlist_name = f"{title} - {artist}"

        except Exception as e:
            self.playlist_name = f"Track {self.track_id}"
            self.show_status(
                f"ERROR: Could not retrieve track name. ({e})")

    def create_local_playlist_folder(self):
        try:
            if not os.path.exists(self.local_playlist_folder):
                os.makedirs(self.local_playlist_folder)

        except Exception as e:
            self.show_status(
                f"ERROR: Could not create local playlist folder. ({e})")

    ######################################################

    def get_spotify_tracks_raw(self):
        try:
            print("Fetching items from Spotify...")
            tracks_fetched = self.fetch_option_tracks()

            for track in tracks_fetched:
                if not track.get('track'):
                    continue

                if track['track']['duration_ms'] == 0 or track['track']['is_local']:
                    continue

                track_data = track['track']
                title = track_data['name']
                artist = ", ".join([artist['name']
                                   for artist in track_data['artists']])
                album = track_data['album']['name']
                albumartist = track_data['album']['artists'][0]['name']
                total_discs = 1
                disc_number = track_data['disc_number']
                total_tracks = track_data['album']['total_tracks']
                track_number = track_data['track_number']
                release_date = track_data['album']['release_date']
                added_at = track.get('added_at') or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                duration = track_data['duration_ms']
                track_url = track_data['external_urls'].get(
                    'spotify', False)
                track_uri = track_data['uri']
                track_id = track_data['id']
                linked_from = track_data.get('linked_from') or {}
                linked_from_id = linked_from.get('id')
                linked_from_uri = linked_from.get('uri')
                match_track_ids, match_track_uris = self.get_track_aliases(track_data)
                artist_ids = [artist['id']
                              for artist in track_data['artists']]
                is_local = track_data['is_local']
                is_playable = track_data.get('is_playable', True)
                save_as = ''

                # 'save_as' will be updated in 'spotify_tracks_fix_save_as' function
                # 'is_playable' value is 'false' for unavailable tracks and 'None' for uploaded tracks

                image = track_data['album']['images'][0]
                for i in track_data['album']['images']:
                    if i['width'] > image['width']:
                        image = i
                image_url = image['url']

                spotify_track = {
                    'title': title,
                    'artist': artist,
                    'album': album,
                    'albumartist': albumartist,
                    'total_discs': total_discs,
                    'disc_number': disc_number,
                    'total_tracks': total_tracks,
                    'track_number': track_number,
                    'release_date': release_date,
                    'added_at': added_at,
                    'duration': duration,
                    'image_url': image_url,
                    'track_url': track_url,
                    'track_uri': track_uri,
                    'track_id': track_id,
                    'linked_from_id': linked_from_id,
                    'linked_from_uri': linked_from_uri,
                    'match_track_ids': match_track_ids,
                    'match_track_uris': match_track_uris,
                    'artist_ids': artist_ids,
                    'is_local': is_local,
                    'is_playable': is_playable,
                    'save_as': save_as
                }

                self.spotify_tracks_raw.append(spotify_track)
                self.spotify_track_ids.update(match_track_ids)

            # Older liked songs should download first.
            self.spotify_tracks_raw.sort(key=lambda a: a.get('added_at') or '')

        except Exception as e:
            self.show_status(
                f"ERROR: Could not get Spotify tracks. ({e})")
            return False

        return True

    def fetch_option_tracks(self):
        if self.option_type in {'playlist', 'move_playlist_matches'}:
            return self.fetch_playlist_tracks()

        if self.option_type == 'track':
            return self.fetch_track()

        return self.fetch_liked_tracks()

    def fetch_liked_tracks(self):
        self.current_liked_tracks_latest_added_at = None
        last_scan_timestamp = self.get_last_liked_tracks_scan_timestamp() if self.option_type == "liked" else None
        self.did_partial_library_scan = bool(last_scan_timestamp)

        response = self.call_spotipy(
            'current_user_saved_tracks', limit=50, offset=0, market=self.config['region'])
        tracks_fetched = []

        while True:
            should_stop = False

            for item in response['items']:
                added_at = item.get('added_at')

                if not self.current_liked_tracks_latest_added_at and added_at:
                    self.current_liked_tracks_latest_added_at = added_at

                if last_scan_timestamp and added_at and added_at <= last_scan_timestamp:
                    should_stop = True
                    break

                tracks_fetched.append(item)

            if should_stop or not response['next']:
                break

            response = self.call_spotipy('next', response)

        return tracks_fetched

    def fetch_playlist_tracks(self):
        response = self.call_spotipy(
            'playlist_tracks', self.playlist_id, market=self.config['region'])
        tracks_fetched = response['items']

        while response['next']:
            response = self.call_spotipy('next', response)
            tracks_fetched.extend(response['items'])

        return tracks_fetched

    def fetch_track(self):
        response = self.call_spotipy('track', self.track_id, market=self.config['region'])
        return [{
            'added_at': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            'track': response,
        }]

    def get_local_tracks_raw(self, root_folder=None, max_depth=None):
        try:
            root_folder = root_folder or self.local_playlist_folder
            root_folder = os.path.abspath(root_folder)

            for folder, subfolders, files in os.walk(root_folder):
                # calculate depth
                current_depth = folder[len(root_folder):].count(os.sep)

                # max_depth: None (scan everything, all subfolders), 0 (only root folder), 1 (root + one level deep), 2 (root + 2 levels deep)

                if max_depth is not None and current_depth >= max_depth:
                    subfolders[:] = []  # stop deeper traversal

                for file in files:
                    file_path = os.path.join(folder, file)
                    file_dir = folder
                    file_name = os.path.splitext(file)[0]
                    file_extension = os.path.splitext(file)[1][1:]

                    if file_extension.lower() == self.config['download_format'].lower():
                        music_file = music_tag.load_file(file_path)

                        tracktitle = str(music_file['tracktitle']).strip()
                        title = tracktitle or str(music_file['title']).strip()
                        artist = str(music_file['artist'])
                        album = str(music_file['album'])
                        track_uri = str(music_file['comment'])
                        track_id = str(music_file['comment']).split(":")[-1]
                        match_track_ids, match_track_uris = self.get_local_track_aliases(track_uri, track_id)
                        duration = round(
                            float(str(music_file['#length'])) * 1000)

                        local_track = {
                            "title": title,
                            "artist": artist,
                            "album": album,
                            "track_uri": track_uri,
                            "track_id": track_id,
                            "match_track_ids": match_track_ids,
                            "match_track_uris": match_track_uris,
                            "duration": duration,
                            "file_path": file_path,
                            "file_dir": file_dir,
                            "file_name": file_name,
                            "file_extension": file_extension
                        }

                        self.local_tracks_raw.append(local_track)
                        self.local_track_ids.update(match_track_ids)

            # sort by title, but if titles are same then sort by artist
            self.local_tracks_raw.sort(key=lambda a: (
                a['title'].lower(), a['artist'].lower()))

        except Exception as e:
            self.status_bar.update(
                self.status_bar_id, description=f"ERROR: Could not get local tracks. ({e})", visible=True)

    def normalize_text(self, value):
        normalized = unicodedata.normalize('NFKC', str(value or ''))
        normalized = normalized.replace('\u2019', "'").replace('\u2018', "'")
        normalized = normalized.replace('\u2013', "-").replace('\u2014', "-")
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized.strip().lower()

    def get_track_aliases(self, track_data):
        track_ids = set()
        track_uris = set()

        for candidate in (track_data, track_data.get('linked_from') or {}):
            candidate_id = str(candidate.get('id') or '').strip()
            candidate_uri = str(candidate.get('uri') or '').strip()

            if candidate_id:
                track_ids.add(candidate_id)

            if candidate_uri:
                track_uris.add(candidate_uri)

        return track_ids, track_uris

    def get_local_track_aliases(self, track_uri, track_id):
        track_ids = set()
        track_uris = set()

        normalized_uri = str(track_uri or '').strip()
        normalized_id = str(track_id or '').strip()

        if normalized_uri:
            track_uris.add(normalized_uri)

        if normalized_id:
            track_ids.add(normalized_id)

        if normalized_uri.startswith('spotify:track:'):
            track_ids.add(normalized_uri.split(':')[-1])

        return track_ids, track_uris

    def tracks_match(self, spotify_track, local_track):
        spotify_track_ids = spotify_track.get('match_track_ids') or {spotify_track.get('track_id')}
        spotify_track_uris = spotify_track.get('match_track_uris') or {spotify_track.get('track_uri')}
        local_track_ids = local_track.get('match_track_ids') or {local_track.get('track_id')}
        local_track_uris = local_track.get('match_track_uris') or {local_track.get('track_uri')}

        if spotify_track_ids & local_track_ids:
            return True

        if spotify_track_uris & local_track_uris:
            return True

        return (
            self.normalize_text(spotify_track['title']) == self.normalize_text(local_track['title']) and
            self.normalize_text(spotify_track['artist']) == self.normalize_text(local_track['artist']) and
            self.normalize_text(spotify_track['album']) == self.normalize_text(local_track['album']) and
            abs(spotify_track['duration'] - local_track['duration']) <= 2000
        )

    def get_track_signature(self, track):
        return (
            self.normalize_text(track['title']),
            self.normalize_text(track['artist']),
            self.normalize_text(track['album']),
            round(track['duration'] / 1000)
        )

    def sanitize_path_component(self, value, fallback="Library"):
        sanitized = re.sub(r'[\\/*?:"<>|]', "", str(value or "")).strip()
        return sanitized or fallback

    def build_non_conflicting_path(self, destination_folder, file_name, file_extension):
        candidate = os.path.join(destination_folder, f"{file_name}.{file_extension}")
        if not os.path.exists(candidate):
            return candidate

        suffix = 1
        while True:
            candidate = os.path.join(
                destination_folder, f"{file_name} ({suffix}).{file_extension}")
            if not os.path.exists(candidate):
                return candidate
            suffix += 1

    def get_archive_folder(self):
        archive_folder = self.config["archive_folder"]
        if not archive_folder:
            raise ValueError("Archive folder is not configured.")

        os.makedirs(archive_folder, exist_ok=True)
        return archive_folder

    def archive_local_track(self, local_track):
        current_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_folder = self.get_archive_folder()
        archive_file_name = f"{local_track['file_name']} ({current_timestamp}).{local_track['file_extension']}"
        destination_file_path = os.path.join(archive_folder, archive_file_name)

        if os.path.exists(local_track['file_path']):
            shutil.move(local_track['file_path'], destination_file_path)

    def hide_path_if_supported(self, path):
        if platform.system() != "Windows":
            return

        FILE_ATTRIBUTE_HIDDEN = 0x02
        FILE_ATTRIBUTE_SYSTEM = 0x04

        try:
            current_attributes = ctypes.windll.kernel32.GetFileAttributesW(path)
            if current_attributes == -1:
                return

            hidden_attributes = current_attributes | FILE_ATTRIBUTE_HIDDEN
            ctypes.windll.kernel32.SetFileAttributesW(path, hidden_attributes)
        except Exception:
            pass

    ######################################################

    def dispose_local_track(self, local_track):
        if not os.path.exists(local_track['file_path']):
            return

        if self.archive_enabled:
            self.archive_local_track(local_track)
            return

        send2trash(local_track['file_path'])

    def spotify_tracks_remove_uploaded(self):
        for spotify_track in self.spotify_tracks_raw:
            if spotify_track['is_local']:
                self.spotify_tracks_uploaded.append(spotify_track)

        for item in self.spotify_tracks_uploaded:
            self.spotify_tracks_raw.remove(item)

    def spotify_tracks_remove_unavailable(self):
        for spotify_track in self.spotify_tracks_raw:
            if not spotify_track['is_playable']:
                self.spotify_tracks_unavailable.append(spotify_track)

        for item in self.spotify_tracks_unavailable:
            self.spotify_tracks_raw.remove(item)

    def spotify_tracks_remove_duplicate(self):
        checked_ids = set()

        for spotify_track in self.spotify_tracks_raw:
            track_aliases = spotify_track.get('match_track_ids') or {spotify_track['track_id']}

            # Treat relinked tracks as the same song if either the playable ID
            # or the original linked_from ID has already been seen.
            if checked_ids & track_aliases:
                self.spotify_tracks_duplicate.append(spotify_track)

            else:
                checked_ids.update(track_aliases)

        for item in self.spotify_tracks_duplicate:
            self.spotify_tracks_raw.remove(item)

    def spotify_tracks_fix_save_as(self):
        checked_titles = set()  # for scenario where two tracks have same title (because two files can't have same filename so we need to change it a bit)
        # for scenario where two tracks have same title and artist (The Avengers from Infinity War)
        checked_titles_artists = set()

        for spotify_track in self.spotify_tracks_raw:
            # for case insensitive comparisons
            title = spotify_track['title'].lower()
            artist = spotify_track['artist'].lower()
            album = spotify_track['album'].lower()
            title_artist = f"{title}, {artist}"

            spotify_track['save_as'] = re.sub(
                r'[\\/*?:"<>|]', "", spotify_track['title'])

            if title in checked_titles:
                save_as = re.sub(
                    r'[\\/*?:"<>|]', "", f"{spotify_track['title']} (by {spotify_track['artist']})")

                spotify_track['save_as'] = save_as
                checked_titles.add(save_as)
            else:
                checked_titles.add(title)

            if title_artist in checked_titles_artists:
                save_as = re.sub(
                    r'[\\/*?:"<>|]', "", f"{spotify_track['title']} (by {spotify_track['artist']}) ({spotify_track['album']})")

                spotify_track['save_as'] = save_as
                checked_titles_artists.add(save_as)
            else:
                checked_titles_artists.add(title_artist)

    ######################################################

    def local_tracks_delete_unmatched(self):
        if self.did_partial_library_scan:
            return

        for local_track in self.local_tracks_raw:
            matched_spotify_track = next(
                (spotify_track for spotify_track in self.spotify_tracks_raw if self.tracks_match(
                    spotify_track, local_track)),
                None
            )

            if not matched_spotify_track:
                self.local_tracks_unmatched.append(local_track)
                self.dispose_local_track(local_track)

        for item in self.local_tracks_unmatched:
            self.local_tracks_raw.remove(item)

    def local_tracks_delete_duplicate(self):
        checked_ids = set()

        for local_track in self.local_tracks_raw:
            local_track_signature = self.get_track_signature(local_track)

            if local_track_signature in checked_ids:
                self.local_tracks_duplicate.append(local_track)
                send2trash(local_track['file_path'])

            else:
                checked_ids.add(local_track_signature)

        for item in self.local_tracks_duplicate:
            self.local_tracks_raw.remove(item)

    def local_tracks_fix_filename(self):
        return

    def move_playlist_matches(self):
        self.init_progress_bars()

        if not self.get_spotify_tracks_raw():
            return False

        self.spotify_tracks_remove_uploaded()
        self.spotify_tracks_remove_unavailable()
        self.spotify_tracks_remove_duplicate()

        self.get_local_tracks_raw(self.source_folder, 0)

        destination_folder = os.path.join(
            self.source_folder,
            self.sanitize_path_component(self.playlist_name, "Playlist")
        )
        os.makedirs(destination_folder, exist_ok=True)

        moved_count = 0
        skipped_count = 0
        matched_paths = set()

        with Live(self.progress_panel_alt, refresh_per_second=10):
            for spotify_track in self.spotify_tracks_raw:
                matched_local_track = next(
                    (
                        local_track for local_track in self.local_tracks_raw
                        if local_track['file_path'] not in matched_paths and self.tracks_match(spotify_track, local_track)
                    ),
                    None
                )

                if not matched_local_track:
                    continue

                matched_paths.add(matched_local_track['file_path'])

                if os.path.abspath(matched_local_track['file_dir']) == os.path.abspath(destination_folder):
                    skipped_count += 1
                    continue

                destination_path = self.build_non_conflicting_path(
                    destination_folder,
                    matched_local_track['file_name'],
                    matched_local_track['file_extension']
                )

                shutil.move(matched_local_track['file_path'], destination_path)
                moved_count += 1

            self.playlist_completed.update(
                self.playlist_completed_id,
                description=(
                    f"[bold green]{self.playlist_name} move completed"
                    f" | Moved: {moved_count} | Already there: {skipped_count}"
                ),
                visible=True
            )

        return True

    ######################################################

    def get_spotify_tracks_to_download(self):
        for spotify_track in self.spotify_tracks_raw:
            matched_local_track = next(
                (local_track for local_track in self.local_tracks_raw if self.tracks_match(
                    spotify_track, local_track)),
                None
            )

            if matched_local_track:
                self.spotify_tracks_already_downloaded.append(spotify_track)
            else:
                self.spotify_tracks_to_download.append(spotify_track)

    def get_spotify_tracks_to_download_incomplete(self):
        return

    ######################################################

    def download_handler(self):
        all_downloads_succeeded = True

        if self.spotify_tracks_to_download:
            with Live(self.progress_panel, refresh_per_second=10):
                for spotify_track in self.spotify_tracks_to_download:
                    self.currently_downloading_track = spotify_track

                    self.status_bar.update(self.status_bar_id, description="", visible=False)
                    self.song_progress.update(
                        self.song_progress_id,
                        description=f"{spotify_track['title']} is downloading")
                    self.metadata_progress.update(self.metadata_progress_id, visible=False)

                    self.playlist_progress.update(
                        self.playlist_progress_id, description=f"{self.playlist_name} | Total Songs: {len(self.spotify_tracks_raw)} | To Download: {len(self.spotify_tracks_to_download) - self.completed_index} | Removed: {len(self.local_tracks_unmatched) + len(self.local_tracks_duplicate)} |")

                    # RUN TASKS
                    download_succeeded = self.downloader()
                    all_downloads_succeeded = all_downloads_succeeded and download_succeeded

                    if download_succeeded:
                        if self.set_file_mtime_from_added_at:
                            self.change_modification_date_to_added_date()
                        self.move_downloaded_track()

                    self.newly_downloaded_track_genres = ''
                    self.newly_downloaded_track_lyrics = ''
                    self.completed_index += 1

                    # UPDATE PROGRESS AFTER SONG DOWNLOAD
                    self.metadata_progress.update(
                        self.metadata_progress_id, visible=False)

                    self.song_progress.update(
                        self.song_progress_id,
                        description=(
                            f"[bold green]{spotify_track['title']} downloaded"
                            if download_succeeded
                            else f"[bold red]{spotify_track['title']} failed"
                        ),
                    )

                    self.playlist_progress.update(
                        self.playlist_progress_id, description=f"{self.playlist_name} | Total Songs: {len(self.spotify_tracks_raw)} | To Download: {len(self.spotify_tracks_to_download) - self.completed_index} | Removed: {len(self.local_tracks_unmatched) + len(self.local_tracks_duplicate)} |")

                # PLAYLIST COMPLETED MESSAGE
                self.playlist_progress.update(
                    self.playlist_progress_id, visible=False)
                self.playlist_completed.update(
                    self.playlist_completed_id, description=f"[bold green]{self.playlist_name} sync completed", visible=True)

        else:
            with Live(self.progress_panel_alt, refresh_per_second=10):
                self.playlist_completed.update(
                    self.playlist_completed_id, description=f"[bold green]{self.playlist_name} sync completed", visible=True)

        return all_downloads_succeeded

    def downloader(self):
        spotify_track = self.currently_downloading_track
        temp_basename = f"{spotify_track['track_id']}_{spotify_track['save_as']}"
        temp_basename = re.sub(r'[\\/*?:"<>|]', "", temp_basename).strip()

        self.temp_download_file = os.path.join(
            self.config['temp_download_folder'], f"{temp_basename}.ogg")
        self.temp_transcode_file = os.path.join(
            self.config['temp_download_folder'], f"{temp_basename}.{self.config['download_format']}")
        self.final_output_file = os.path.join(
            self.local_playlist_folder, f"{spotify_track['save_as']}.{self.config['download_format']}")

        # create temp folder
        if not os.path.exists(self.config['temp_download_folder']):
            os.makedirs(self.config['temp_download_folder'])
            self.hide_path_if_supported(self.config['temp_download_folder'])

        # clear stale temp files for this track
        for temp_file in (self.temp_download_file, self.temp_transcode_file):
            if os.path.exists(temp_file):
                Path(temp_file).unlink()

        # download audio, transcode temp downloaded file to a useable format, fetch genres and lyrics, add metadata
        if not self.download_audio_stream():
            return False

        if not self.transcode_audio():
            return False

        self.fetch_genres()
        self.fetch_lyrics()

        if not self.add_metadata():
            return False

        return True

    def download_audio_stream(self):
        try:
            spotify_track = self.currently_downloading_track

            quality_options = {
                'normal': AudioQuality.NORMAL,
                'high': AudioQuality.HIGH,
            }
            download_quality = quality_options[self.config['download_quality']]

            track_signature = TrackId.from_base62(spotify_track['track_id'])
            stream = self.librespot_session.content_feeder().load(track_signature,
                                                                  VorbisOnlyAudioQuality(
                                                                      download_quality),
                                                                  False, None)

            stream_size = stream.input_stream.size
            stream_iter = stream.input_stream.stream()

            total_for_bar = stream_size if stream_size and stream_size > 0 else None
            if hasattr(self.download_progress, "reset"):
                self.download_progress.reset(
                    self.download_progress_id,
                    total=total_for_bar,
                    completed=0,
                    visible=True,
                    description="Downloading audio stream",
                )
            else:
                self.download_progress.update(
                    self.download_progress_id,
                    total=total_for_bar,
                    completed=0,
                    visible=True,
                    description="Downloading audio stream",
                )

            with open(self.temp_download_file, 'wb') as file:
                while True:
                    chunk = stream_iter.read(self.config['chunk_size'])
                    if not chunk:
                        break
                    file.write(chunk)
                    self.download_progress.update(
                        self.download_progress_id,
                        advance=len(chunk),
                    )

            self.download_progress.update(
                self.download_progress_id, visible=False)

            return True

        except Exception as e:
            self.status_bar.update(
                self.status_bar_id, description=f"ERROR: Could not download audio stream. ({e})", visible=True)
            return False

    def transcode_audio(self):
        try:
            self.metadata_progress.update(
                self.metadata_progress_id, description="Transcoding audio", visible=True)

            codecs = {
                'm4a': 'aac',
                'mp3': 'libmp3lame',
                'ogg': 'copy',
                'opus': 'libopus',
            }

            bitrates = {
                'normal': '96k',
                'high': '160k',
            }

            file_codec = codecs[self.config['download_format']]

            if file_codec != 'copy':
                bitrate = bitrates[self.config['download_quality']]
            else:
                bitrate = None

            output_params = ['-c:a', file_codec]
            if bitrate:
                output_params += ['-b:a', bitrate]
            if self.config['download_format'] == 'm4a':
                output_params += ['-movflags', '+faststart']

            try:
                ffmpy_method = ffmpy.FFmpeg(
                    global_options=['-y', '-hide_banner', '-loglevel error'],
                    inputs={self.temp_download_file: None},
                    outputs={self.temp_transcode_file: output_params}
                )

                ffmpy_method.run()

                if Path(self.temp_download_file).exists():
                    Path(self.temp_download_file).unlink()

                self.metadata_progress.stop_task(self.metadata_progress_id)
                return True

            except ffmpy.FFExecutableNotFoundError:
                self.status_bar.update(
                    self.status_bar_id, description=f'Skipping {file_codec.upper()} conversion (FFMPEG not found)', visible=True)
                return False

        except Exception as e:
            self.status_bar.update(
                self.status_bar_id, description=f"ERROR: Could not transcode audio stream. ({e})", visible=True)
            return False

    def fetch_genres(self):
        try:
            self.metadata_progress.update(
                self.metadata_progress_id, description="Fetching genres")

            response = self.call_spotipy(
                'artists', self.currently_downloading_track['artist_ids'])
            artists_fetched = response.get('artists', [])

            artists_genres = [artist['genres'] for artist in artists_fetched]

            genres = ''
            for artist_genre in artists_genres:
                for genre in artist_genre:
                    genres += genre.title() + ', '

            self.newly_downloaded_track_genres = genres.rstrip(', ')

            self.metadata_progress.stop_task(self.metadata_progress_id)

        except Exception as e:
            self.status_bar.update(
                self.status_bar_id, description=f"MINOR: Could not fetch genres for '{self.currently_downloading_track['title']}'", visible=True)

    def fetch_lyrics(self):
        try:
            self.metadata_progress.update(
                self.metadata_progress_id, description="Fetching lyrics")

            _, data = self.fetch_url(
                url=f"https://spclient.wg.spotify.com/color-lyrics/v2/track/{self.currently_downloading_track['track_id']}")

            if data:
                try:
                    lyrics_raw = data['lyrics']['lines']

                except KeyError:
                    raise ValueError("Lyrics not available")

                lyrics = []
                if (data['lyrics']['syncType'] == "UNSYNCED"):
                    for line in lyrics_raw:
                        lyrics.append(line['words'] + '\n')

                elif (data['lyrics']['syncType'] == "LINE_SYNCED"):
                    for line in lyrics_raw:
                        timestamp = int(line['startTimeMs'])
                        ts_minutes = str(math.floor(
                            timestamp / 60000)).zfill(2)
                        ts_seconds = str(math.floor(
                            (timestamp % 60000) / 1000)).zfill(2)
                        ts_millis = str(math.floor(timestamp % 1000))[
                            :2].zfill(2)
                        lyrics.append(
                            f'[{ts_minutes}:{ts_seconds}.{ts_millis}]' + line['words'] + '\n')

                self.newly_downloaded_track_lyrics = ''.join(lyrics)

            self.metadata_progress.stop_task(self.metadata_progress_id)

        except (Exception, ValueError) as e:
            self.status_bar.update(
                self.status_bar_id, description=f"MINOR: Could not fetch lyrics for '{self.currently_downloading_track['title']}'", visible=True)

    def add_metadata(self):
        try:
            self.metadata_progress.update(
                self.metadata_progress_id, description="Adding metadata")

            spotify_track = self.currently_downloading_track

            # add tags
            music_file = music_tag.load_file(self.temp_transcode_file)
            music_file['tracktitle'] = spotify_track['title']
            music_file['title'] = spotify_track['title']
            music_file['artist'] = spotify_track['artist']
            music_file['album'] = spotify_track['album']
            music_file['albumartist'] = spotify_track['albumartist']
            music_file['totaldiscs'] = spotify_track['total_discs']
            music_file['discnumber'] = spotify_track['disc_number']
            music_file['totaltracks'] = spotify_track['total_tracks']
            music_file['tracknumber'] = spotify_track['track_number']
            music_file['comment'] = spotify_track.get('linked_from_uri') or spotify_track['track_uri']
            music_file['composer'] = spotify_track['release_date']
            music_file['year'] = spotify_track['release_date'].split('-')[0]
            music_file['genre'] = self.newly_downloaded_track_genres
            music_file['lyrics'] = self.newly_downloaded_track_lyrics
            music_file.save()

            # add cover
            cover_response = requests.get(spotify_track['image_url'])
            cover_response.raise_for_status()

            cover_bytes = cover_response.content
            content_type = cover_response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            cover_format = {
                'image/jpeg': 'jpeg',
                'image/jpg': 'jpeg',
                'image/png': 'png',
            }.get(content_type, 'jpeg')

            if self.config['download_format'] == 'mp3':
                id3_tags = mutagen.id3.ID3(self.temp_transcode_file)
                id3_tags.delall('APIC')
                id3_tags.add(mutagen.id3.APIC(
                    encoding=3,
                    mime=content_type or f'image/{cover_format}',
                    type=mutagen.id3.PictureType.COVER_FRONT,
                    desc='Cover',
                    data=cover_bytes
                ))
                id3_tags.save(self.temp_transcode_file, v2_version=3)

            else:
                music_file = music_tag.load_file(self.temp_transcode_file)
                music_file['artwork'] = music_tag.Artwork(cover_bytes, fmt=cover_format)
                music_file.save()

            self.metadata_progress.stop_task(self.metadata_progress_id)
            return True

        except Exception as e:
            self.status_bar.update(
                self.status_bar_id, description=f"ERROR: Could not write metadata to audio file. ({e})", visible=True)
            return False

    def change_modification_date_to_added_date(self):
        if not self.set_file_mtime_from_added_at:
            return

        try:
            self.metadata_progress.update(self.metadata_progress_id, description="Updating modification date", visible=True)

            timestamp_raw = self.currently_downloading_track['added_at']
            ts_utc = datetime.strptime(timestamp_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            timestamp_epoch = ts_utc.timestamp()

            os.utime(self.temp_transcode_file, (timestamp_epoch, timestamp_epoch))

            self.metadata_progress.stop_task(self.metadata_progress_id)

        except Exception as e:
            self.status_bar.update(
                self.status_bar_id, description=f"ERROR: Could not update modification date of audio file. ({e})", visible=True)

    def move_downloaded_track(self):
        try:
            self.metadata_progress.update(
                self.metadata_progress_id, description="Moving file to destination folder")

            file_path_old = self.temp_transcode_file
            file_path_new = self.final_output_file

            if not os.path.exists(self.local_playlist_folder):
                os.makedirs(self.local_playlist_folder)

            if self.option_type == 'track' and os.path.exists(file_path_new):
                file_name = Path(file_path_new).stem
                file_extension = Path(file_path_new).suffix.lstrip('.')
                file_path_new = self.build_non_conflicting_path(
                    self.local_playlist_folder,
                    file_name,
                    file_extension
                )

            shutil.move(file_path_old, file_path_new)

            self.metadata_progress.stop_task(self.metadata_progress_id)

        except Exception as e:
            self.status_bar.update(
                self.status_bar_id, description=f"ERROR: ({e})", visible=True)

    def remove_temp_download_folder(self):
        if os.path.exists(self.config['temp_download_folder']):
            send2trash(self.config['temp_download_folder'])

    ######################################################

    def fetch_url(self, url, retry_count=0):
        access_token = self.spotipy_session.auth_manager.get_access_token(
            as_dict=False)
        headers = {
            'Authorization': f"Bearer {access_token}",
            'Accept-Language': "en",
            'Accept': 'application/json',
            'app-platform': 'WebPlayer'
        }

        response = requests.get(url, headers=headers)
        response_text = response.text

        try:
            response_json = response.json()

        except json.decoder.JSONDecodeError:
            response_json = {"error": {"status": "unknown",
                                       "message": response_text or "received an empty response"}}

        if response.status_code >= 400 or 'error' in response_json:
            error_status = response_json.get('error', {}).get('status', response.status_code)
            error_message = response_json.get('error', {}).get('message', response.reason or 'unknown error')
            retry_limit = self.config.get('retry_attempts', 0)
            retry_delay = 5

            if int(error_status) == 429:
                retry_limit = max(retry_limit, 3)
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        retry_delay = max(1, int(float(retry_after)))
                    except ValueError:
                        retry_delay = 5
                else:
                    retry_delay = min(30, 2 ** retry_count)

            if retry_count < retry_limit:
                self.show_status(
                    f"ERROR: Could not fetch the requested URL. (retry {retry_count + 1}) ({error_status}): {error_message}")
                time.sleep(retry_delay)
                return self.fetch_url(url, retry_count + 1)

            raise Exception(
                f"Reason: {error_status} | Error message: {error_message}")

        return response_text, response_json

    def format_seconds(self, sec):
        val = math.floor(sec)

        s = math.floor(val % 60)
        val -= s
        val /= 60

        m = math.floor(val % 60)
        val -= m
        val /= 60

        h = math.floor(val)

        if h == 0 and m == 0 and s == 0:
            return "0s"
        elif h == 0 and m == 0:
            return f'{s}s'.zfill(2)
        elif h == 0:
            return f'{m}'.zfill(2) + ':' + f'{s}'.zfill(2)
        else:
            return f'{h}'.zfill(2) + ':' + f'{m}'.zfill(2) + ':' + f'{s}'.zfill(2)

    def format_bytes(self, size_in_bytes):
        if size_in_bytes == 0:
            return "0b"

        # Define the units and their corresponding labels
        units = ["b", "kb", "mb", "gb", "tb", "pb", "eb", "zb", "yb"]

        # Determine the appropriate unit
        unit_index = 0
        while size_in_bytes >= 1024 and unit_index < len(units) - 1:
            size_in_bytes /= 1024.0
            unit_index += 1

        # Format the result with one decimal place using f-string
        size_formatted = f"{size_in_bytes:.1f}{units[unit_index]}"

        return size_formatted

    def update_window_title(self, text):
        if platform.system() != "Windows":
            return
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(
                f"Unify Script by HammadXP | {text}")
        except Exception:
            pass

    def splash(self):
        print("\n")
        print("=================================\n"
              "|                               |\n"
              "|       Unify for Spotify       |\n"
              "|       by HammadXP             |\n"
              "|                               |\n"
              "=================================")
        print("\n")

    def clear(self):
        if platform.system() == "Windows":
            os.system("cls")
        else:
            os.system("clear")

    ######################################################
