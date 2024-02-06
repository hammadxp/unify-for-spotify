Unify is a python script for keeping a copy of your Spotify music collection or playlists locally and keep them in sync.

The script fetches data for all tracks of a Spotify playlist (using SpotiPy), then does it's magic of filtering for the tracks that have not been saved yet. It will ignore tracks that have already been saved, are unavailable or were uploaded by the user. The playlists will be organized into folders based on the playlist name.

## Features

- Handles duplicate tracks that were added twice to the same playlist
- Handles tracks with same title, or artist, or even both and rename files in such situations
- Updates file modification date to match with the date when the track was added to the playlist
- Keeps tracks in their respective folders based on the playlist name

## Notes

- Any extra tracks present in playlist folder locally that are not present in Spotify playlist will be removed
- Uploaded tracks will be ignored because they can't be recognized by `librespot-python`
- The script relies on the list of playlists you provide to it in the `config.json` file, so saving a song individually won't be possible, you will need to add it to a playlist first
- The script has only been tested with MP3 files, on Windows with Python v3.10

\* you can modify the script to get around these hiccups

## Setup

Make sure you have the following installed on your system:

- Python
- pip

### Step 1: Clone the Repository

- `git clone https://github.com/hammadxp/unify-for-spotify`
- `cd unify-for-spotify`

### Step 2: Fill credentials and config

Move `.env` and `config.json` files from `example_files` folder to parent folder where `script.py` resides.

- Fill your Spotify `USERNAME`, `PASSWORD`, `CLIENT_ID` and `CLIENT_SECRET` in `.env` file (required for `SpotiPy` library)
- Fill script settings in `config.json`

### Step 3: Create a Virtual Environment

- `python -m venv .venv`

This will create a virtual environment named `.venv` in the script directory.

### Step 4: Activate the Virtual Environment

- `.venv\Scripts\activate`

You should see the virtual environment's name in your shell prompt.

### Step 5: Install Dependencies

- `pip install -r requirements.txt`

### Step 6: Run the Script

- `python script.py`

### Step 7: Deactivate the Virtual Environment

When you're done, deactivate the virtual environment:

- `deactivate`

A virtual environment is only needed for the initial setup of the app for installing dependencies. Afterwards you can just run the script directly by double clicking `script.py`.

To switch account or sign-out of the app, you can simply delete `credentials.json` file which stores the current user session.

## Upcoming features

- CLI interface for running different operations
- Save individual tracks
- Provide a playlist URL directly in CLI without having to specify it in `config.json` first
- Download user's Liked Songs playlist
- Download unavailable tracks by changing region

## Other

- I'm not good at documenting stuff so apologies if something is not clear
- I create scripts for fun that would help me automate my stuff and I occasionally share them on GitHub :)

---

As always, if you have any features in mind, or something is not working, or you're stuck, let me know in Issues section, I will help you out! :smile:
