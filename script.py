import argparse

from unify import Unify


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-type",
        choices=["liked", "playlist"],
        help="Sync source type: liked or playlist",
    )
    parser.add_argument(
        "--playlist-url",
        help="Spotify playlist URL when --source-type=playlist",
    )
    parser.add_argument(
        "--destination-folder",
        help="Destination folder for downloaded tracks",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    app = Unify()

    app.create_spotipy_session()
    app.login_to_librespot()
    app.load_config()
    app.init_state()

    if args.source_type:
        app.source_type = args.source_type
        if app.source_type == 'liked':
            app.playlist_name = 'Liked Songs'
    else:
        app.prompt_sync_mode()

    if app.source_type == 'playlist':
        if args.playlist_url:
            app.playlist_url = args.playlist_url.strip()
            app.get_playlist_id()
            if not app.playlist_id:
                raise ValueError("Invalid --playlist-url provided.")
        else:
            app.prompt_playlist_url()
        app.get_playlist_name()

    if args.destination_folder:
        app.local_playlist_folder = args.destination_folder.strip().strip('"')
    else:
        app.prompt_destination_folder()

    app.create_local_playlist_folder()

    app.update_window_title(app.playlist_name)
    app.init_progress_bars()

    if not app.get_spotify_tracks_raw():
        app.update_window_title('Failed.')
        input('\nFailed.')
        return

    app.get_local_tracks_raw()

    app.spotify_tracks_remove_uploaded()
    app.spotify_tracks_remove_unavailable()
    app.spotify_tracks_remove_duplicate()
    app.spotify_tracks_fix_save_as()

    app.local_tracks_delete_unmatched()
    app.local_tracks_delete_duplicate()
    app.get_spotify_tracks_to_download()
    app.get_spotify_tracks_to_download_incomplete()

    app.download_handler()

    app.remove_temp_download_folder()
    app.update_window_title('Finished.')
    input('\nFinished.')


if __name__ == "__main__":
    main()
