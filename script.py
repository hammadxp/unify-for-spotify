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
    parser.add_argument(
        "--region",
        help="Spotify market/region code used for track lookups",
    )
    parser.add_argument(
        "--download-format",
        choices=["aac", "fdk_aac", "m4a", "mp3", "ogg", "opus", "vorbis"],
        help="Output audio format",
    )
    parser.add_argument(
        "--download-quality",
        choices=["normal", "high"],
        help="Spotify stream quality to download",
    )
    parser.add_argument(
        "--transcode-bitrate",
        help="Target bitrate for transcoded files",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        help="Chunk size in bytes for audio stream downloads",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        help="Number of retry attempts for failed requests",
    )
    parser.add_argument(
        "--archive-folder",
        help="Folder used for archiving replaced or removed tracks",
    )
    parser.add_argument(
        "--temp-download-folder",
        help="Folder used for temporary download and transcode files",
    )
    return parser.parse_args()


def apply_config_overrides(app, args):
    config_overrides = {
        "region": args.region,
        "download_format": args.download_format,
        "download_quality": args.download_quality,
        "transcode_bitrate": args.transcode_bitrate,
        "chunk_size": args.chunk_size,
        "retry_attempts": args.retry_attempts,
        "archive_folder": args.archive_folder.strip().strip('"') if args.archive_folder else None,
        "temp_download_folder": args.temp_download_folder.strip().strip('"') if args.temp_download_folder else None,
    }

    for key, value in config_overrides.items():
        if value is not None:
            app.config[key] = value


def configure_source(app, args):
    if args.source_type:
        app.source_type = args.source_type
        if app.source_type == "liked":
            app.playlist_name = "Liked Songs"
        return

    app.prompt_sync_mode()


def configure_playlist(app, args):
    if app.source_type != "playlist":
        return

    if args.playlist_url:
        app.playlist_url = args.playlist_url.strip()
        app.get_playlist_id()
        if not app.playlist_id:
            raise ValueError("Invalid --playlist-url provided.")
    else:
        app.prompt_playlist_url()

    app.get_playlist_name()


def configure_destination_folder(app, args):
    if args.destination_folder:
        app.local_playlist_folder = args.destination_folder.strip().strip('"')
        return

    app.prompt_destination_folder()


def configure_runtime_options(app, args):
    apply_config_overrides(app, args)
    configure_source(app, args)
    configure_playlist(app, args)
    configure_destination_folder(app, args)


def main():
    args = parse_args()
    app = Unify()

    app.create_spotipy_session()
    app.login_to_librespot()
    app.load_config()
    app.init_state()
    configure_runtime_options(app, args)

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
