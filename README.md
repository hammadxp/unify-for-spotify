Unify is a python script for keeping a copy of your Spotify music collection locally and keeping it in sync.

The script can download Liked Songs, an individual playlist, or a single track. It can also organize existing local downloads by matching them against a Spotify playlist and moving matches into a playlist-named folder.

## Features

- Handles duplicate tracks that were added twice to the same playlist
- Handles tracks with same title, or artist, or even both and rename files in such situations
- Updates file modification date to match with the date when the track was added to the playlist
- Keeps tracks in their respective folders based on the playlist name
- Lets you choose folders with the system folder picker instead of typing paths
- Includes an interactive option selector that works with arrow keys and Enter

## Notes

- Any extra tracks present in playlist folder locally that are not present in Spotify playlist will be removed
- Uploaded tracks will be ignored because they can't be recognized by `librespot-python`
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

Move `.env` and `config.json` files from `example_files` folder to the project root where `script.py` resides.

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

## Available options

- Download your Liked Songs library
- Download a single track
- Download an individual playlist
- Move unorganized downloaded songs to a playlist folder

## Other

- I'm not good at documenting stuff so apologies if something is not clear
- I create scripts for fun that would help me automate my stuff and I occasionally share them on GitHub :)

---

As always, if you have any features in mind, or something is not working, or you're stuck, let me know in Issues section, I will help you out! :smile:
