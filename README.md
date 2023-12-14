A python script for keeping Spotify playlists in sync with local music library.

The script fetches data for all tracks of a Spotify playlist (using SpotiPy), then do it's magic and find tracks that are not present locally and then saves them (using Librespot-python). The playlists are organized into folders based on the playlist name. It will filter out any tracks that have already been downloaded, are unavailable or were uploaded by the user.

## Features

- Keeps Spotify playlists in sync with local folders organized by playlist names
- Handles tracks with same title, or artist, or even both and rename files accordingly
- Handles duplicate tracks that were added twice to the same playlist
- Updates file modification date to match with the date when the track was added to the playlist

## Notes

- Any extra tracks present in playlist folder locally that are not present in Spotify playlist will be removed
- Uploaded tracks will be ignored because they can't recognized by Librespot-python
- The script has only been tested with MP3 files

\* you can modify the script to get around above hiccups

## Install

Make sure the required Python libraries are installed, see requirements.txt.

## Config

- Fill your Spotify `CLIENT_ID` and `CLIENT_SECRET` in `.env` file (required for SpotiPy library)
- Fill script settings in `config.json`

\* you can get these two files from "example_files" directory

## Usage

- Once properly configured, simply launch the script with:

  `py script.py`

\* during first run, the script will present a login prompt for your Spotify `username` and `password` (required for Librespot-python), the credentials will be safely stored in `credentials.json`, you can delete this file if you want to sign out

## Upcoming features

- Download user's Liked Songs library
- Download unavailable tracks by changing region for those tracks

## Other facts

- I'm not good at documenting stuff so apologies if something is not clear
- I create scripts for fun that would help me automate my stuff and I occasionally share them on GitHub :)

---

As always, if you have any features in mind, or something is not working, or you're stuck, let me know in Issues section, I will help you out! :smile:
