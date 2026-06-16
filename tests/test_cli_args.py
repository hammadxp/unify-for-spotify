from argparse import Namespace

from cli_args import apply_config_runtime_defaults, configure_playlist


class FakePlaylistApp:
    def __init__(self):
        self.option_type = "playlist"
        self.loaded_config = {}
        self.playlist_url = ""
        self.playlist_id = ""
        self.playlist_name = ""
        self.playlist_jobs = []

    def get_playlist_id(self):
        self.playlist_id = self.playlist_url.rsplit("/", 1)[-1].split("?", 1)[0]

    def get_playlist_name(self):
        self.playlist_name = f"Playlist {self.playlist_id}"


def build_args(**overrides):
    defaults = {
        "option_type": "playlist",
        "playlist_url": None,
        "track_url": None,
        "destination_folder": None,
        "source_folder": None,
        "enable_archive": None,
        "archive_folder": None,
        "set_file_mtime_from_added_at": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def test_config_playlist_url_string_expands_to_ordered_playlist_jobs():
    app = FakePlaylistApp()
    app.loaded_config = {
        "--playlist-url": (
            "https://open.spotify.com/playlist/first?si=1 "
            "https://open.spotify.com/playlist/second?si=2 "
            "https://open.spotify.com/playlist/third?si=3"
        )
    }
    args = build_args()

    apply_config_runtime_defaults(app, args)
    configure_playlist(app, args)

    assert [job["id"] for job in app.playlist_jobs] == ["first", "second", "third"]
    assert [job["name"] for job in app.playlist_jobs] == [
        "Playlist first",
        "Playlist second",
        "Playlist third",
    ]
    assert app.playlist_url == "https://open.spotify.com/playlist/first?si=1"
    assert app.playlist_id == "first"
    assert app.playlist_name == "Playlist first"
