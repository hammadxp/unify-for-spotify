from unify import Unify


def main():
    app = Unify()

    app.create_spotipy_session()
    app.login_to_librespot()
    app.load_config()

    for _, playlist_url in app.config['playlists'].items():
        app.init_state()

        app.playlist_url = playlist_url
        app.get_playlist_id()
        app.get_playlist_name()
        app.create_local_playlist_folder()

        app.update_window_title(f"Playlist: {app.playlist_name}")
        app.init_progress_bars()

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

    app.remove_temp_download_folder()
    app.update_window_title('Finished.')
    input('\nFinished.')


if __name__ == "__main__":
    main()
