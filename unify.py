import os
import re
import json
import math
import time
import ctypes
import platform
import requests
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

import ffmpy
import music_tag
from send2trash import send2trash

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality

from rich.console import Group
from rich.panel import Panel
from rich.live import Live
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


class Unify:
    def __init__(self):
        self.init_state()

    def init_state(self):
        # Playlist info
        self.playlist_url = ''
        self.playlist_id = ''
        self.playlist_name = ''
        self.local_playlist_folder = ''

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
        self.currently_downloading_track = {}
        self.newly_downloaded_track = {}
        self.newly_downloaded_track_genres = ''
        self.newly_downloaded_track_lyrics = ''

        # Progress
        self.completed_index = 0
        self.progress_bar_text = ''

    def create_spotipy_session(self):
        try:
            load_dotenv()

            client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")

            client_credentials_manager = SpotifyClientCredentials(
                client_id=client_id, client_secret=client_secret)
            
            self.spotipy_session = spotipy.Spotify(
                client_credentials_manager=client_credentials_manager)
        
        except Exception as e:
            self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not create SpotiPy session. ({e})", visible=True)
        
    def login_to_librespot(self):
        # check if the user has already logged in to librespot with their Spotify credentials, if so, retrieve session details from that file
        if os.path.isfile("credentials.json"):
            try:
                self.librespot_session = Session.Builder().stored_file().create()
                return
            except RuntimeError:
                pass

        # if user hasn't logged in before, ask for their Spotify username and password
        while True:
            spotify_username = input("Your Spotify username: ")
            spotify_password = input("Your Spotify password: ")
            
            try:
                self.librespot_session = Session.Builder().user_pass(spotify_username, spotify_password).create()
                return
            except RuntimeError:
                pass

    def load_config(self):
        try:
            with open('config.json', 'r') as config_file:
                self.config = json.load(config_file)

        except FileNotFoundError:
            self.status_bar.update(self.status_bar_id, description="ERROR: Config file not found. Make sure cmd is opened in the Unify script's folder and config.json exists in that folder.", visible=True)

    def init_progress_bars(self):
        ### CREATE PROGRESS BARS
        self.status_bar = Progress(TextColumn("{task.description}"))

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

        ### INITIALIZE PLAYLIST PROGRESS
        self.playlist_progress_id = self.playlist_progress.add_task("")
        self.playlist_completed_id = self.playlist_completed.add_task("", visible=False)

        ### PROGRESS PANEL
        self.progress_panel = Panel(
            Group(
                self.status_bar,
                Panel(Group(self.song_progress, self.download_progress, self.metadata_progress)),
                Panel(Group(self.playlist_progress, self.playlist_completed))
            )
        )
        
        self.progress_panel_alt = Panel(self.playlist_completed)

    ######################################################

    def get_playlist_id(self):
        try:
            if match := re.match(r"https://open.spotify.com/playlist/(.*)\?", self.playlist_url):
                self.playlist_id = match.groups()[0]
            else:
                raise ValueError()
        
        except ValueError as e:
            self.status_bar.update(self.status_bar_id, description=f"ERROR: Bad playlist URL format. ({self.playlist_url})", visible=True)

    def get_playlist_name(self):
        try:
            self.playlist_name = self.spotipy_session.user_playlist(
            user=None, playlist_id=self.playlist_id, fields="name")['name']

        except Exception as e:
            self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not retrieve playlist name. ({e})", visible=True)

    def create_local_playlist_folder(self):
        try:
            self.local_playlist_folder = os.path.join(
                self.config['library_folder'], self.playlist_name)

            if not os.path.exists(self.local_playlist_folder):
                os.makedirs(self.local_playlist_folder)

        except Exception as e:
            self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not create local playlist folder. ({e})", visible=True)

    ######################################################

    def get_spotify_tracks_raw(self):
            try:
                response = self.spotipy_session.playlist_tracks(
                    self.playlist_id, market=self.config['region'])
                tracks_fetched = response['items']

                while response['next']:
                    response = self.spotipy_session.next(response)
                    tracks_fetched.extend(response['items'])

                for track in tracks_fetched:
                    if track['track']['duration_ms'] == 0 or track['track']['is_local']:
                        continue

                    title = track['track']['name']
                    artist = ", ".join([artist['name'] for artist in track['track']['artists']])
                    album = track['track']['album']['name']
                    albumartist = track['track']['album']['artists'][0]['name']
                    total_discs = 1
                    disc_number = track['track']['disc_number']
                    total_tracks = track['track']['album']['total_tracks']
                    track_number = track['track']['track_number']
                    release_date = track['track']['album']['release_date']
                    added_at = track['added_at']
                    duration = track['track']['duration_ms']
                    track_url = track['track']['external_urls'].get('spotify', False)
                    track_uri = track['track']['uri']
                    track_id = track['track']['id']
                    artist_ids = [artist['id'] for artist in track['track']['artists']]
                    is_local = track['track']['is_local']
                    is_playable = track['track'].get('is_playable', True)
                    save_as = ''
                    
                    # 'save_as' will be updated in 'spotify_tracks_fix_save_as' function
                    # 'is_playable' value is 'false' for unavailable tracks and 'None' for uploaded tracks

                    image = track['track']['album']['images'][0]
                    for i in track['track']['album']['images']:
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
                        'artist_ids': artist_ids,
                        'is_local': is_local,
                        'is_playable': is_playable,
                        'save_as': save_as
                    }

                    self.spotify_tracks_raw.append(spotify_track)
                    self.spotify_track_ids.add(spotify_track['track_id'])

                # sort by title, but if titles are same then sort by artist
                self.spotify_tracks_raw.sort(key=lambda a: (
                    a['title'].lower(), a['artist'].lower()))
            
            except Exception as e:
                self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not get Spotify tracks. ({e})", visible=True)

    def get_local_tracks_raw(self):
            try:
                for folder, subfolders, files in os.walk(self.local_playlist_folder):
                    for file in files:
                        file_path = os.path.join(folder, file)
                        file_dir = folder
                        file_name = os.path.splitext(file)[0]
                        file_extension = os.path.splitext(file)[1][1:]

                        if file_extension == self.config['download_format']:
                            music_file = music_tag.load_file(file_path)

                            title = str(music_file['title'])
                            artist = str(music_file['artist'])
                            album = str(music_file['album'])
                            track_uri = str(music_file['comment'])
                            track_id = str(music_file['comment']).split(":")[-1]
                            # track_id = str(music_file['comment']).split(":")[-1] if len(str(music_file['comment']).split(":")) > 1 else ""
                            duration = round(float(str(music_file['#length'])) * 1000)

                            local_track = {
                                "title": title,
                                "artist": artist,
                                "album": album,
                                "track_uri": track_uri,
                                "track_id": track_id,
                                "duration": duration,
                                "file_path": file_path,
                                "file_dir": file_dir,
                                "file_name": file_name,
                                "file_extension": file_extension
                            }

                            self.local_tracks_raw.append(local_track)
                            self.local_track_ids.add(local_track['track_id'])

                # sort by title, but if titles are same then sort by artist
                self.local_tracks_raw.sort(key=lambda a: (
                    a['title'].lower(), a['artist'].lower()))
            
            except Exception as e:
                self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not get local tracks. ({e})", visible=True)

    ######################################################

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
            # for finding local tracks that have same ids
            if spotify_track['track_id'] in checked_ids:
                self.spotify_tracks_duplicate.append(spotify_track)

            else:
                checked_ids.add(spotify_track['track_id'])

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
        for local_track in self.local_tracks_raw:
            # for finding local tracks whose id do not match with any track in spotify playlist
            if local_track['track_id'] not in self.spotify_track_ids or "spotify" not in local_track['track_uri']:
                self.local_tracks_unmatched.append(local_track)

                # delete local_track
                if os.path.exists(local_track['file_path']):
                    send2trash(local_track['file_path'])

        for item in self.local_tracks_unmatched:
            self.local_tracks_raw.remove(item)

    def local_tracks_delete_duplicate(self):
        checked_ids = set()

        for local_track in self.local_tracks_raw:
            # for finding local tracks that have same ids
            if local_track['track_id'] in checked_ids:
                self.local_tracks_duplicate.append(local_track)

                # delete local_track
                if os.path.exists(local_track['file_path']):
                    send2trash(local_track['file_path'])

            else:
                checked_ids.add(local_track['track_id'])

        for item in self.local_tracks_duplicate:
            self.local_tracks_raw.remove(item)

    def local_tracks_fix_filename(self):
        for local_track in self.local_tracks_raw:
            for spotify_track in self.spotify_tracks_raw:
                # find specific track from spotify playlist
                if local_track['track_id'] == spotify_track['track_id']:

                    # find track whose file_name is different from save_as
                    if local_track['file_name'] != spotify_track['save_as']:
                        # rename local_track
                        if os.path.exists(local_track['file_path']):
                            os.rename(local_track['file_path'], os.path.join(
                                local_track['file_dir'], spotify_track['save_as'] + local_track['file_extension']))

    ######################################################

    def get_spotify_tracks_to_download(self):
        for spotify_track in self.spotify_tracks_raw:
            # find tracks that have not been downloaded yet
            if spotify_track['track_id'] not in self.local_track_ids:
                self.spotify_tracks_to_download.append(spotify_track)

            else:
                self.spotify_tracks_already_downloaded.append(spotify_track)

    def get_spotify_tracks_to_download_incomplete(self):
        for spotify_track in self.spotify_tracks_raw:
            for local_track in self.local_tracks_raw:
                # find specific track from spotify playlist
                if spotify_track['track_id'] == local_track['track_id']:

                    # find track whose duration is incomplete and need to be re-downloaded
                    if spotify_track['duration'] != local_track['duration']:
                        # duration difference in milliseconds, 1000ms = 1s
                        if (spotify_track['duration'] - local_track['duration']) > 1000:
                            self.spotify_tracks_incomplete.append(
                                spotify_track)
                            self.spotify_tracks_to_download.append(
                                spotify_track)

    ######################################################

    def download_handler(self):
        if self.spotify_tracks_to_download:
            with Live(self.progress_panel):
                for spotify_track in self.spotify_tracks_to_download:
                    self.currently_downloading_track = spotify_track

                    ### INITIALIZE SONG PROGRESS
                    self.status_bar_id = self.status_bar.add_task("", visible=False)
                    self.song_progress_id = self.song_progress.add_task(f"{spotify_track['title']} is downloading")
                    self.download_progress_id = self.download_progress.add_task("Initializing")
                    self.metadata_progress_id = self.metadata_progress.add_task("", visible=False)

                    self.playlist_progress.update(self.playlist_progress_id, description=f"Playlist: {self.playlist_name} | Total Songs: {len(self.spotify_tracks_raw)} | To Download: {len(self.spotify_tracks_to_download) - self.completed_index} | Unavailable: {len(self.spotify_tracks_unavailable)} |")

                    ### RUN TASKS
                    self.downloader()
                    self.change_modification_date_to_added_date()
                    self.move_downloaded_track()
                    self.newly_downloaded_track_genres = ''
                    self.newly_downloaded_track_lyrics = ''
                    self.completed_index += 1

                    ### UPDATE PROGRESS AFTER SONG DOWNLOAD
                    self.metadata_progress.update(self.metadata_progress_id, visible=False)

                    self.song_progress.stop_task(self.song_progress_id)
                    self.song_progress.update(self.song_progress_id, description=f"[bold green]{spotify_track['title']} downloaded")

                    self.playlist_progress.update(self.playlist_progress_id, description=f"Playlist: {self.playlist_name} | Total Songs: {len(self.spotify_tracks_raw)} | To Download: {len(self.spotify_tracks_to_download) - self.completed_index} | Unavailable: {len(self.spotify_tracks_unavailable)} |")
                
                # PLAYLIST COMPLETED MESSAGE
                self.playlist_progress.update(self.playlist_progress_id, visible=False)
                self.playlist_completed.update(self.playlist_completed_id, description=f"[bold green]{self.playlist_name} playlist downloaded", visible=True)
        
        else:
            with Live(self.progress_panel_alt):
                self.playlist_completed.update(self.playlist_completed_id, description=f"[bold green]{self.playlist_name} playlist downloaded", visible=True)

    def downloader(self):
        # localize variables for repetitive usage
        spotify_track = self.currently_downloading_track
        self.temp_download_file = os.path.join(self.config['temp_download_folder'], f"temp.{self.config['download_format']}")

        # create temp folder
        if not os.path.exists(self.config['temp_download_folder']):
            os.makedirs(self.config['temp_download_folder'])

        # remove existing temp file
        if os.path.exists(self.temp_download_file):
            send2trash(self.temp_download_file)

        # download audio, transcode temp downloaded file to a useable format, fetch genres and lyrics, add metadata
        self.download_audio_stream()
        self.transcode_audio()
        self.fetch_genres()
        self.fetch_lyrics()
        self.add_metadata()

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
                                                VorbisOnlyAudioQuality(download_quality),
                                                False, None)

            stream_size = stream.input_stream.size
            downloaded = 0

            with open(self.temp_download_file, 'wb') as file:
                b = 0
                while b < 5:
                    chunk = stream.input_stream.stream().read(self.config['chunk_size'])
                    file.write(chunk)

                    self.download_progress.update(
                        self.download_progress_id,
                        description="Downloading audio stream",
                        total=stream_size,
                        advance=len(chunk)
                    )
                    self.download_progress.stop_task(self.download_progress_id)
                    
                    downloaded += len(chunk)
                    b += 1 if chunk == b'' else 0
            
            self.download_progress.update(self.download_progress_id, visible=False)

        except Exception as e:
            self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not download audio stream. ({e})", visible=True)

    def transcode_audio(self):
        try:
            self.metadata_progress.update(self.metadata_progress_id, description="Transcoding audio", visible=True)

            self.temp_transcode_file = os.path.join(self.config['temp_download_folder'], f"{self.currently_downloading_track['save_as']}.{self.config['download_format']}")

            codecs = {
                'aac': 'aac',
                'fdk_aac': 'libfdk_aac',
                'm4a': 'aac',
                'mp3': 'libmp3lame',
                'ogg': 'copy',
                'opus': 'libopus',
                'vorbis': 'copy',
            }

            bitrates = {
                'normal': '96k',
                'high': '160k',
            }

            file_codec = codecs.get(self.config['download_format'], 'copy')

            if file_codec != 'copy':
                bitrate = self.config['transcode_bitrate']
                bitrate = bitrates[self.config['download_quality']]
            else:
                bitrate = None

            output_params = ['-c:a', file_codec]
            if bitrate:
                output_params += ['-b:a', bitrate]

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

            except ffmpy.FFExecutableNotFoundError:
                self.status_bar.update(self.status_bar_id, description=f'Skipping {file_codec.upper()} conversion (FFMPEG not found)', visible=True)
        
        except Exception as e:
            self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not transcode audio stream. ({e})", visible=True)

    def fetch_genres(self):
            try:
                self.metadata_progress.update(self.metadata_progress_id, description="Fetching genres")

                response = self.spotipy_session.artists(artists=self.currently_downloading_track['artist_ids'])
                artists_fetched = response['artists']

                artists_genres = [artist['genres'] for artist in artists_fetched]

                genres = ''
                for artist_genre in artists_genres:
                    for genre in artist_genre:
                        genres += genre.title() + ', '
                
                self.newly_downloaded_track_genres = genres.rstrip(', ')

                self.metadata_progress.stop_task(self.metadata_progress_id)
            
            except Exception as e:
                self.status_bar.update(self.status_bar_id, description=f"MINOR: Could not fetch genres for '{self.currently_downloading_track['title']}'", visible=True)

    def fetch_lyrics(self):
            try:
                self.metadata_progress.update(self.metadata_progress_id, description="Fetching lyrics")

                _, data = self.fetch_url(url = f"https://spclient.wg.spotify.com/color-lyrics/v2/track/{self.currently_downloading_track['track_id']}")

                if data:
                    try:
                        lyrics_raw = data['lyrics']['lines']

                    except KeyError:
                        raise ValueError("Lyrics not available")

                    lyrics = []
                    if(data['lyrics']['syncType'] == "UNSYNCED"):
                        for line in lyrics_raw:
                            lyrics.append(line['words'] + '\n')

                    elif(data['lyrics']['syncType'] == "LINE_SYNCED"):
                        for line in lyrics_raw:
                            timestamp = int(line['startTimeMs'])
                            ts_minutes = str(math.floor(timestamp / 60000)).zfill(2)
                            ts_seconds = str(math.floor((timestamp % 60000) / 1000)).zfill(2)
                            ts_millis = str(math.floor(timestamp % 1000))[:2].zfill(2)
                            lyrics.append(f'[{ts_minutes}:{ts_seconds}.{ts_millis}]' + line['words'] + '\n')
                        
                    self.newly_downloaded_track_lyrics = ''.join(lyrics)

                self.metadata_progress.stop_task(self.metadata_progress_id)

            except (Exception, ValueError) as e:
                self.status_bar.update(self.status_bar_id, description=f"MINOR: Could not fetch lyrics for '{self.currently_downloading_track['title']}'", visible=True)

    def add_metadata(self):
            try:
                self.metadata_progress.update(self.metadata_progress_id, description="Adding metadata")

                spotify_track = self.currently_downloading_track

                # add tags
                music_file = music_tag.load_file(self.temp_transcode_file)
                music_file['tracktitle'] = spotify_track['title']
                music_file['artist'] = spotify_track['artist']
                music_file['album'] = spotify_track['album']
                music_file['albumartist'] = spotify_track['albumartist']
                music_file['totaldiscs'] = spotify_track['total_discs']
                music_file['discnumber'] = spotify_track['disc_number']
                music_file['totaltracks'] = spotify_track['total_tracks']
                music_file['tracknumber'] = spotify_track['track_number']
                music_file['comment'] = spotify_track['track_uri']
                music_file['composer'] = spotify_track['release_date']
                music_file['year'] = spotify_track['release_date'].split('-')[0]
                music_file['genre'] = self.newly_downloaded_track_genres
                music_file['lyrics'] = self.newly_downloaded_track_lyrics
                music_file.save()

                # add cover
                cover = requests.get(spotify_track['image_url']).content
                music_file = music_tag.load_file(self.temp_transcode_file)
                music_file['artwork'] = cover
                music_file.save()

                self.metadata_progress.stop_task(self.metadata_progress_id)
            
            except Exception as e:
                self.status_bar.update(self.status_bar_id, description="ERROR: Could not write metadata to audio file. Make sure ffmpeg is installed and added to your PATH.", visible=True)

    def change_modification_date_to_added_date(self):
            try:
                self.metadata_progress.update(self.metadata_progress_id, description="Updating modification date")

                timestamp_raw = self.currently_downloading_track['added_at']
                timestamp = datetime.strptime(timestamp_raw, "%Y-%m-%dT%H:%M:%SZ")
                timestamp_adjusted = timestamp + timedelta(hours=5)
                timestamp_epoch = timestamp_adjusted.timestamp()
                mdate_P1 = timestamp_adjusted.strftime("%Y-%m-%d")
                mdate_P2 = timestamp_adjusted.strftime("%Y-%m-%d %H:%M:%S")

                os.utime(self.temp_transcode_file, (timestamp_epoch, timestamp_epoch))

                self.metadata_progress.stop_task(self.metadata_progress_id)

            except Exception as e:
                self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not update modification date of audio file. ({e})", visible=True)

    def move_downloaded_track(self):
            try:
                self.metadata_progress.update(self.metadata_progress_id, description="Moving file to playlist folder")

                file_path_old = self.temp_transcode_file
                file_path_new = os.path.join(
                    self.local_playlist_folder, f"{self.currently_downloading_track['save_as']}.{self.config['download_format']}")

                if not os.path.exists(self.local_playlist_folder):
                    os.makedirs(self.local_playlist_folder)

                os.replace(file_path_old, file_path_new)

                self.metadata_progress.stop_task(self.metadata_progress_id)
            
            except Exception as e:
                self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not move downloaded audio file to playlist folder. ({e})", visible=True)

    ######################################################

    def fetch_url(self, url):
        headers = {
            'Authorization': f"Bearer {self.librespot_session.tokens().get_token('user-read-email','playlist-read-private','user-library-read', 'user-follow-read').access_token}",
            'Accept-Language': "en",
            'Accept': 'application/json',
            'app-platform': 'WebPlayer'
        }

        response = requests.get(url, headers=headers)
        response_text = response.text
        retry_count = 0

        try:
            response_json = response.json()

        except json.decoder.JSONDecodeError:
            response_json = {"error": {"status": "unknown", "message": "received an empty response"}}

            if not response_json or 'error' in response_json:
                if retry_count < (self.config['retry_attempts'] - 1):
                    self.status_bar.update(self.status_bar_id, description=f"ERROR: Could not fetch the requested URL. (retry {retry_count + 1}) ({response_json['error']['status']}): {response_json['error']['message']}", visible=True)
                    time.sleep(5)

                    return self.invoke_url(url, retry_count + 1)

                raise Exception(f"Reason: {response_json['error']['status']} | Error message: {response_json['error']['message']}")

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
        ctypes.windll.kernel32.SetConsoleTitleW(
            f"Unify Script by HammadXP | {text}")

    def splash():
        print("\n")
        print("=================================\n"
            "|                               |\n"
            "|       Unify for Spotify       |\n"
            "|       by HammadXP             |\n"
            "|                               |\n"
            "=================================")
        print("\n")

    def clear():
        if platform.system() == "Windows":
            os.system("cls")
        else:
            os.system("clear")

    ######################################################
