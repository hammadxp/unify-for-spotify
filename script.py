import os
import re
import json
import ctypes
import spotipy
import music_tag
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from datetime import datetime, timedelta
from colorama import init, Fore, Back, Style
from send2trash import send2trash


class Container:
    def __init__(self):
        self.init_state()

    def init_state(self):
        self.playlist_url = ''
        self.playlist_id = ''
        self.playlist_name = ''
        self.local_playlist_folder = ''

        self.spotify_tracks_raw = []
        self.spotify_tracks_already_downloaded = []
        self.spotify_tracks_incomplete = []
        self.spotify_tracks_duplicate = []
        self.spotify_tracks_uploaded = []
        self.spotify_tracks_unavailable = []
        self.spotify_tracks_deleted = []
        self.spotify_tracks_to_download = []

        self.local_tracks_raw = []
        self.local_tracks_already_downloaded = []
        self.local_tracks_duplicate = []
        self.local_tracks_uploaded = []
        self.local_tracks_unmatched = []

        self.spotify_track_ids = set()
        self.local_track_ids = set()

        self.currently_downloading_track = {}
        self.newly_downloaded_track = {}
        self.newly_downloaded_track_genres = ''
        self.newly_downloaded_track_lyrics = ''
        self.completed_index = 0

        self.progress_bar_text = ''

    def load_config(self):
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)

                # download folder should be same as in DownOnSpot's config
                self.download_client_download_folder = config['download_client_download_folder']
                self.library_folder = config['library_folder']
                self.music_files_extension = config['music_files_extension']

                # it's just the text that appears in cmd window's title
                self.script_owner = config['script_owner']
                # 'region' is only used for tracks info, it can't be used for download of unavailable tracks from other regions
                self.region = config['region']

                self.playlists = config['playlists']
                self.download_client = config['download_client']

        except FileNotFoundError:
            print("CONFIG FILE NOT FOUND. Make sure cmd is opened in the Unify script's folder and config.json exists in that folder.")

    def create_spotipy_session(self):
        load_dotenv()

        client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")

        client_credentials_manager = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret)
        self.spotipy_session = spotipy.Spotify(
            client_credentials_manager=client_credentials_manager)

    ######################################################

    def get_playlist_id(self):
        if match := re.match(r"https://open.spotify.com/playlist/(.*)\?", self.playlist_url):
            self.playlist_id = match.groups()[0]
        else:
            raise ValueError("Bad URL format !!!")

    def get_playlist_name(self):
        self.playlist_name = self.spotipy_session.user_playlist(
            user=None, playlist_id=self.playlist_id, fields="name")['name']

    def create_local_playlist_folder(self):
        self.local_playlist_folder = os.path.join(
            self.library_folder, self.playlist_name)

        if not os.path.exists(self.local_playlist_folder):
            os.makedirs(self.local_playlist_folder)

    ######################################################

    def get_spotify_tracks_raw(self):
        response = self.spotipy_session.playlist_tracks(
            self.playlist_id, market=self.region)
        tracks_fetched = response['items']

        while response['next']:
            response = self.spotipy_session.next(response)
            tracks_fetched.extend(response['items'])

        for track in tracks_fetched:
            title = track['track']['name']
            artist = ", ".join([artist['name']
                               for artist in track['track']['artists']])
            album = track['track']['album']['name']
            disc_number = track['track']['disc_number']
            total_tracks = track['track']['album']['total_tracks']
            track_number = track['track']['track_number']
            release_date = track['track']['album']['release_date']
            added_at = track['added_at']
            duration = track['track']['duration_ms']
            track_url = track['track']['external_urls'].get('spotify', False)
            track_id = track['track']['id']
            artist_ids = [artist['id']
                          for artist in track['track']['artists']]
            is_local = track['track']['is_local']
            # is_playable value is 'false' for unavailable tracks, and not present on uploaded tracks?
            is_playable = track['track'].get('is_playable', True)
            # for 'uploaded' tracks, it's value is 'None'
            save_as = ''  # will update it in 'spotify_tracks_fix_save_as' function

            spotify_track = {
                'title': title,
                'artist': artist,
                'album': album,
                'disc_number': disc_number,
                'total_tracks': total_tracks,
                'track_number': track_number,
                'release_date': release_date,
                'added_at': added_at,
                'duration': duration,
                'track_url': track_url,
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

    def get_local_tracks_raw(self):
        for folder, subfolders, files in os.walk(self.local_playlist_folder):
            for file in files:
                file_path = os.path.join(folder, file)
                file_dir = folder
                file_name = os.path.splitext(file)[0]
                file_extension = os.path.splitext(file)[1]

                if file_extension in self.music_files_extension:
                    music_file = music_tag.load_file(file_path)

                    title = str(music_file['title'])
                    artist = str(music_file['artist'])
                    album = str(music_file['album'])
                    comment = str(music_file['comment'])
                    duration = round(float(str(music_file['#length'])) * 1000)

                    local_track = {
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "track_id": comment,
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

    def spotify_tracks_remove_deleted(self):
        for spotify_track in self.spotify_tracks_raw:
            if spotify_track['title'] == '' and spotify_track['artist'] == '' and spotify_track['album'] == '':
                self.spotify_tracks_deleted.append(spotify_track)

        for item in self.spotify_tracks_deleted:
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
            if local_track['track_id'] not in self.spotify_track_ids:
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

    def update_window_title(self, text):
        ctypes.windll.kernel32.SetConsoleTitleW(
            f"Spotify Script by {self.script_owner} | {text}")

    def empty_local_temporary_download_folder(self):
        for folder, subfolders, files in os.walk(self.download_client_download_folder):
            for file in files:
                file_path = os.path.join(folder, file)
                send2trash(file_path)

    ######################################################

    def downloader(self):
        if not self.download_client:
            raise ValueError(
                "Download client is not specified. Please provide 'download_client' a value in config.json file.")

        self.update_window_title(self.progress_bar_text)

        download_client_to_use = ''

        if self.download_client == 'Zotify':
            download_client_to_use = 'zotify'
        elif self.download_client == 'DownOnSpot':
            download_client_to_use = 'down_on_spot'

        os.system(
            f"{download_client_to_use} \"{self.currently_downloading_track['track_url']}\"")
        
        self.get_genres()

    def get_newly_downloaded_track(self):
        isCorrectFolder = False

        for folder, subfolders, files in os.walk(self.download_client_download_folder):
            isCorrectFolder = True

            for file in files:
                file_path = os.path.join(folder, file)
                file_dir = folder
                file_name = os.path.splitext(file)[0]
                file_extension = os.path.splitext(file)[1]

                if file_extension in self.music_files_extension:
                    music_file = music_tag.load_file(file_path)

                    title = str(music_file['title'])
                    artist = str(music_file['artist'])
                    album = str(music_file['album'])
                    comment = str(music_file['comment'])
                    duration = round(float(str(music_file['#length'])) * 1000)

                    self.newly_downloaded_track = {
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "track_id": comment,
                        "duration": duration,
                        "file_path": file_path,
                        "file_dir": file_dir,
                        "file_name": file_name,
                        "file_extension": file_extension
                    }

                if file_extension in [".lrc"]:
                    with open(file_path, 'r', encoding='utf-8') as lrc_file:
                        lrc_contents = lrc_file.read()
                        self.newly_downloaded_track_lyrics = lrc_contents

        if not isCorrectFolder:
            raise ValueError(
                "Temporary download folder is empty, make sure you specified the correct folder in config.json file.")

    def get_genres(self):
        response = self.spotipy_session.artists(artists=self.currently_downloading_track['artist_ids'])
        artists_fetched = response['artists']
        artists_genres = [artist['genres'] for artist in artists_fetched]

        genres = ''
        for artist_genre in artists_genres:
            for genre in artist_genre:
                genres += genre.title() + ', '
        
        genres = genres.rstrip(', ')

        self.newly_downloaded_track_genres = genres

    def edit_metadata(self):
        music_file = music_tag.load_file(
            self.newly_downloaded_track['file_path'])

        music_file['title'] = self.currently_downloading_track['title']
        music_file['artist'] = self.currently_downloading_track['artist']
        music_file['album'] = self.currently_downloading_track['album']
        music_file['comment'] = self.currently_downloading_track['track_id']
        music_file['totaldiscs'] = 1
        music_file['discnumber'] = self.currently_downloading_track['disc_number']
        music_file['totaltracks'] = self.currently_downloading_track['total_tracks']
        music_file['tracknumber'] = self.currently_downloading_track['track_number']
        music_file['year'] = self.currently_downloading_track['release_date']
        music_file['composer'] = self.currently_downloading_track['release_date']
        music_file['genre'] = self.newly_downloaded_track_genres
        music_file['lyrics'] = self.newly_downloaded_track_lyrics
        music_file.save()

        # music_tag somehow writes comment tag value twice, so we need to later select first one

    def change_modification_date_to_added_date(self):
        timestamp_raw = self.currently_downloading_track['added_at']
        timestamp = datetime.strptime(timestamp_raw, "%Y-%m-%dT%H:%M:%SZ")
        timestamp_adjusted = timestamp + timedelta(hours=5)
        timestamp_epoch = timestamp_adjusted.timestamp()
        mdate_P1 = timestamp_adjusted.strftime("%Y-%m-%d")
        mdate_P2 = timestamp_adjusted.strftime("%Y-%m-%d %H:%M:%S")

        os.utime(
            self.newly_downloaded_track['file_path'], (timestamp_epoch, timestamp_epoch))

    def move_downloaded_track(self):
        file_path_old = self.newly_downloaded_track['file_path']
        file_path_new = os.path.join(
            self.local_playlist_folder, self.newly_downloaded_track['file_name'] + self.newly_downloaded_track['file_extension'])

        if not os.path.exists(self.local_playlist_folder):
            os.makedirs(self.local_playlist_folder)

        os.replace(file_path_old, file_path_new)

    def download_handler(self):
        for spotify_track in self.spotify_tracks_to_download:
            self.currently_downloading_track = spotify_track

            self.progress_bar_text = f"\nPlaylist: {self.playlist_name} (Total Songs: {len(self.spotify_tracks_raw)} | To Download: {len(self.spotify_tracks_to_download) - self.completed_index}) (Unavailable: {len(self.spotify_tracks_unavailable)}) | Downloading: {spotify_track['save_as']}\n"

            self.empty_local_temporary_download_folder()
            self.downloader()
            self.get_newly_downloaded_track()
            self.edit_metadata()
            self.change_modification_date_to_added_date()
            self.move_downloaded_track()
            self.empty_local_temporary_download_folder()
            self.newly_downloaded_track_lyrics = ''

            self.completed_index += 1

        if len(self.spotify_tracks_to_download) == self.completed_index and len(self.spotify_tracks_unavailable) == 0:
            print(
                f"{self.playlist_name.ljust(30)} {Fore.GREEN + 'DOWNLOADED' + Style.RESET_ALL}")

        if len(self.spotify_tracks_to_download) == self.completed_index and len(self.spotify_tracks_unavailable) > 0:
            print(f"{self.playlist_name.ljust(30)} {Fore.GREEN + 'DOWNLOADED' + Fore.YELLOW + ' (Unavailable tracks skipped)' + Style.RESET_ALL}")

    ######################################################


def main():
    app = Container()

    app.load_config()
    app.create_spotipy_session()
    init()  # For colorama

    for _, playlist_url in app.playlists.items():
        app.init_state()

        app.playlist_url = playlist_url
        app.get_playlist_id()
        app.get_playlist_name()
        app.create_local_playlist_folder()

        app.update_window_title(f"Processing: {app.playlist_name}")
        app.get_spotify_tracks_raw()
        app.get_local_tracks_raw()

        app.spotify_tracks_remove_uploaded()
        app.spotify_tracks_remove_unavailable()
        app.spotify_tracks_remove_duplicate()
        app.spotify_tracks_fix_save_as()

        app.local_tracks_delete_unmatched()
        app.local_tracks_delete_duplicate()
        app.local_tracks_fix_filename()

        app.get_spotify_tracks_to_download()
        app.get_spotify_tracks_to_download_incomplete()

        app.download_handler()

    app.update_window_title('Finished.')
    input('\nFinished.')


if __name__ == "__main__":
    main()
