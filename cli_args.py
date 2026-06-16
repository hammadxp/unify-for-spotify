import argparse
import os

VALID_OPTION_TYPES = {"track", "playlist", "liked_full", "liked_partial", "move_playlist_matches"}


def normalize_cli_path(path_value):
    if not path_value:
        return None

    return os.path.abspath(os.path.expanduser(path_value.strip().strip('"')))


def get_config_value(app, *keys):
    for key in keys:
        if key in app.loaded_config and app.loaded_config[key] is not None:
            return app.loaded_config[key]

    return None


def normalize_config_text(value):
    if value is None:
        return None

    return str(value).strip()


def normalize_config_bool(value, key):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False

    raise ValueError(f"Config value '{key}' must be true or false.")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--option-type",
        choices=["track", "playlist", "liked_full", "liked_partial", "move_playlist_matches"],
        help="Option type: liked_full, liked_partial, playlist, track, or move_playlist_matches",
    )
    parser.add_argument(
        "--playlist-url",
        nargs="+",
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
        default=None,
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
        default=None,
        help="Set each file's modification time from the track's Spotify added_at time (UTC, displayed in your local timezone). Off by default.",
    )

    args = parser.parse_args()

    args.config_path = normalize_cli_path(args.config_path)
    args.archive_folder = normalize_cli_path(args.archive_folder)
    args.temp_download_folder = normalize_cli_path(args.temp_download_folder)

    return args


def apply_config_runtime_defaults(app, args):
    if args.option_type is None:
        option_type = normalize_config_text(get_config_value(app, "option_type", "option-type"))
        if option_type:
            if option_type not in VALID_OPTION_TYPES:
                valid_options = ", ".join(sorted(VALID_OPTION_TYPES))
                raise ValueError(f"Config value 'option_type' must be one of: {valid_options}.")
            args.option_type = option_type

    if args.playlist_url is None:
        playlist_url = get_config_value(app, "playlist_url", "playlist-url")
        if isinstance(playlist_url, list):
            args.playlist_url = [
                normalized_url
                for url in playlist_url
                if (normalized_url := normalize_config_text(url))
            ]
        else:
            normalized_url = normalize_config_text(playlist_url)
            if normalized_url:
                args.playlist_url = [normalized_url]

    if args.track_url is None:
        args.track_url = normalize_config_text(get_config_value(app, "track_url", "track-url"))

    if args.destination_folder is None:
        destination_folder = normalize_config_text(get_config_value(
            app, "destination_folder", "destination-folder"))
        if destination_folder:
            args.destination_folder = normalize_cli_path(destination_folder)

    if args.source_folder is None:
        source_folder = normalize_config_text(get_config_value(app, "source_folder", "source-folder"))
        if source_folder:
            args.source_folder = normalize_cli_path(source_folder)

    if args.enable_archive is None:
        args.enable_archive = normalize_config_bool(
            get_config_value(app, "enable_archive", "enable-archive"),
            "enable_archive",
        )

    if args.archive_folder is None:
        archive_folder = normalize_config_text(get_config_value(app, "archive_folder", "archive-folder"))
        if archive_folder:
            args.archive_folder = normalize_cli_path(archive_folder)

    if args.set_file_mtime_from_added_at is None:
        args.set_file_mtime_from_added_at = normalize_config_bool(
            get_config_value(app, "set_file_mtime_from_added_at", "set-file-mtime-from-added-at"),
            "set_file_mtime_from_added_at",
        )


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

    app.set_file_mtime_from_added_at = bool(args.set_file_mtime_from_added_at)

    app.archive_enabled = bool(args.enable_archive)
    app.config["archive_folder"] = args.archive_folder if app.archive_enabled else None


def validate_runtime_options(args):
    if args.archive_folder and not args.enable_archive:
        raise ValueError("--archive-folder requires --enable-archive or config enable_archive=true.")

    if args.enable_archive and not args.archive_folder:
        raise ValueError("--enable-archive requires --archive-folder or config archive_folder.")


def configure_option(app, args):
    if args.option_type:
        app.option_type = args.option_type

        if app.option_type in {"liked_full", "liked_partial"}:
            app.playlist_name = "Liked Songs"
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
        playlist_urls = args.playlist_url
        if isinstance(playlist_urls, str):
            playlist_urls = [playlist_urls]

        playlist_urls = [url.strip() for url in playlist_urls if url.strip()]
        if app.option_type == "move_playlist_matches" and len(playlist_urls) > 1:
            raise ValueError("--option-type move_playlist_matches accepts one --playlist-url.")

        app.playlist_url = playlist_urls[0]
        app.get_playlist_id()

        if not app.playlist_id:
            raise ValueError("Invalid --playlist-url provided.")

        app.playlist_jobs = [
            {
                "url": app.playlist_url,
                "id": app.playlist_id,
                "name": None,
            }
        ]

        for playlist_url in playlist_urls[1:]:
            app.playlist_url = playlist_url
            app.get_playlist_id()

            if not app.playlist_id:
                raise ValueError(f"Invalid --playlist-url provided: {playlist_url}")

            app.playlist_jobs.append({
                "url": playlist_url,
                "id": app.playlist_id,
                "name": None,
            })
    else:
        app.prompt_playlist_url()
        app.playlist_jobs = [
            {
                "url": app.playlist_url,
                "id": app.playlist_id,
                "name": None,
            }
        ]

    app.get_playlist_name()
    app.playlist_jobs[0]["name"] = app.playlist_name

    for playlist_job in app.playlist_jobs[1:]:
        app.playlist_url = playlist_job["url"]
        app.playlist_id = playlist_job["id"]
        app.get_playlist_name()
        playlist_job["name"] = app.playlist_name

    first_playlist_job = app.playlist_jobs[0]
    app.playlist_url = first_playlist_job["url"]
    app.playlist_id = first_playlist_job["id"]
    app.playlist_name = first_playlist_job["name"]


def configure_destination_folder(app, args):
    if app.option_type not in {"track", "playlist", "liked_full", "liked_partial"}:
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
    apply_config_runtime_defaults(app, args)
    validate_runtime_options(args)
    apply_config_overrides(app, args)
    configure_option(app, args)
    configure_track(app, args)
    configure_playlist(app, args)
    configure_destination_folder(app, args)
    configure_source_folder(app, args)
