import os

from cli_args import configure_runtime_options, parse_args
from unify import Unify
from utils import pause_for_user


def sync_current_selection(app):
    app.create_local_playlist_folder()
    app.prepare_runtime_state()

    app.update_window_title(app.playlist_name)
    app.init_progress_bars()

    if not app.get_spotify_tracks_raw():
        app.update_window_title("Failed.")
        return False

    if app.option_type != "track":
        app.get_local_tracks_raw()

        app.spotify_tracks_remove_uploaded()
        app.spotify_tracks_remove_unavailable()
        app.spotify_tracks_remove_duplicate()
        app.spotify_tracks_fix_save_as()

        app.local_tracks_delete_unmatched()
        app.local_tracks_delete_duplicate()

        app.get_spotify_tracks_to_download()
        app.get_spotify_tracks_to_download_incomplete()
    else:
        app.spotify_tracks_fix_save_as()
        app.spotify_tracks_to_download = list(app.spotify_tracks_raw)

    sync_succeeded = app.download_handler()

    if sync_succeeded:
        app.remember_liked_tracks_scan_timestamp()

    app.remove_temp_download_folder()

    return sync_succeeded


def sync_playlist_jobs(app):
    playlist_jobs = app.playlist_jobs or [
        {
            "url": app.playlist_url,
            "id": app.playlist_id,
            "name": app.playlist_name,
        }
    ]

    if len(playlist_jobs) == 1:
        return sync_current_selection(app)

    destination_root = app.local_playlist_folder
    all_succeeded = True

    for playlist_job in playlist_jobs:
        app.reset_sync_collections()
        app.playlist_url = playlist_job["url"]
        app.playlist_id = playlist_job["id"]
        app.playlist_name = playlist_job["name"]
        app.local_playlist_folder = os.path.join(
            destination_root,
            app.sanitize_path_component(app.playlist_name, "Playlist")
        )

        if not sync_current_selection(app):
            all_succeeded = False

    return all_succeeded


def main():
    args = parse_args()
    app = Unify()

    app.create_spotipy_session()
    app.load_config(args.config_path)
    configure_runtime_options(app, args)

    if app.option_type == "move_playlist_matches":
        app.update_window_title("Move Playlist Matches")
        app.move_playlist_matches()
        app.update_window_title("Finished.")
        pause_for_user()
        return

    app.login_to_librespot()

    if app.option_type == "playlist":
        sync_playlist_jobs(app)
    else:
        sync_current_selection(app)

    app.update_window_title("Finished.")
    pause_for_user()


if __name__ == "__main__":
    main()
