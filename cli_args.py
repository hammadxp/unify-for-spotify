import argparse
import os


def normalize_cli_path(path_value):
    if not path_value:
        return None

    return os.path.abspath(os.path.expanduser(path_value.strip().strip('"')))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--option-type",
        choices=["track", "playlist", "liked", "liked_no_cache", "move_playlist_matches"],
        help="Option type: liked, liked_no_cache, playlist, track, or move_playlist_matches",
    )
    parser.add_argument(
        "--playlist-url",
        help="Spotify playlist URL when the selected option requires a playlist",
    )
    parser.add_argument(
        "--track-url",
        help="Spotify track URL when --option-type=track",
    )
    parser.add_argument(
        "--destination-folder",
        help="Destination folder for downloaded tracks",
    )
    parser.add_argument(
        "--source-folder",
        help="Source folder for local tracks when --option-type=move_playlist_matches",
    )
    parser.add_argument(
        "--region",
        help="Spotify market/region code used for track lookups",
    )
    parser.add_argument(
        "--download-format",
        choices=["mp3", "m4a", "ogg", "opus"],
        help="Output container/codec: mp3 (MP3), m4a (AAC), ogg (Vorbis remux), opus (Opus transcode)",
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
        "--config-path",
        help="Optional path to a JSON config file with saved runtime settings",
    )
    parser.add_argument(
        "--enable-archive",
        action="store_true",
        help="Archive unmatched local tracks instead of sending them to the recycle bin",
    )
    parser.add_argument(
        "--archive-folder",
        help="Folder used for archiving replaced or removed tracks (requires --enable-archive)",
    )
    parser.add_argument(
        "--temp-download-folder",
        help="Folder used for temporary download and transcode files",
    )
    parser.add_argument(
        "--set-file-mtime-from-added-at",
        action="store_true",
        help="Set each file's modification time from the track's Spotify added_at time (UTC, displayed in your local timezone). Off by default.",
    )

    args = parser.parse_args()

    args.config_path = normalize_cli_path(args.config_path)
    args.archive_folder = normalize_cli_path(args.archive_folder)
    args.temp_download_folder = normalize_cli_path(args.temp_download_folder)

    if args.archive_folder and not args.enable_archive:
        parser.error("--archive-folder requires --enable-archive.")

    if args.enable_archive and not args.archive_folder:
        parser.error("--enable-archive requires --archive-folder.")

    return args


def apply_config_overrides(app, args):
    config_overrides = {
        "region": args.region,
        "download_format": args.download_format,
        "download_quality": args.download_quality,
        "transcode_bitrate": args.transcode_bitrate,
        "chunk_size": args.chunk_size,
        "retry_attempts": args.retry_attempts,
        "temp_download_folder": args.temp_download_folder,
    }

    for key, value in config_overrides.items():
        if value is not None:
            app.config[key] = value

    app.set_file_mtime_from_added_at = args.set_file_mtime_from_added_at

    app.archive_enabled = args.enable_archive
    app.config["archive_folder"] = args.archive_folder if args.enable_archive else None


def configure_option(app, args):
    if args.option_type:
        app.option_type = args.option_type

        if app.option_type == "liked":
            app.playlist_name = "Liked Songs"
        elif app.option_type == "liked_no_cache":
            app.playlist_name = "Liked Songs (No Cache)"
        return

    app.prompt_option_selection()


def configure_track(app, args):
    if app.option_type != "track":
        return

    if args.track_url:
        app.track_url = args.track_url.strip()
        app.get_track_id()

        if not app.track_id:
            raise ValueError("Invalid --track-url provided.")
    else:
        app.prompt_track_url()

    app.get_track_name()


def configure_playlist(app, args):
    if app.option_type not in {"playlist", "move_playlist_matches"}:
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
    if app.option_type not in {"track", "playlist", "liked", "liked_no_cache"}:
        return

    if args.destination_folder:
        app.local_playlist_folder = normalize_cli_path(args.destination_folder)
        return

    app.prompt_destination_folder()


def configure_source_folder(app, args):
    if app.option_type != "move_playlist_matches":
        return

    if args.source_folder:
        app.source_folder = normalize_cli_path(args.source_folder)
        return

    app.prompt_source_folder()


def configure_runtime_options(app, args):
    apply_config_overrides(app, args)
    configure_option(app, args)
    configure_track(app, args)
    configure_playlist(app, args)
    configure_destination_folder(app, args)
    configure_source_folder(app, args)
