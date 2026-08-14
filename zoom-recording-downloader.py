#!/usr/bin/env python3

# Program Name: zoom-recording-downloader.py
# Description:  Zoom Recording Downloader is a cross-platform Python script
#               that uses Zoom's API (v2) to download and organize all
#               cloud recordings from a Zoom account onto local storage.
#               This Python script uses the OAuth method of accessing the Zoom API
# Created:      2020-04-26
# Author:       Ricardo Rodrigues
# Website:      https://github.com/ricardorodrigues-ca/zoom-recording-downloader
# Forked from:  https://gist.github.com/danaspiegel/c33004e52ffacb60c24215abf8301680

# System modules
import argparse
import base64
import json
import os
import re as regex
import signal
import sys as system
import time
from datetime import datetime, date, timezone, timedelta

# Installed modules
import dateutil.parser as parser
import pathvalidate as path_validate
import requests
import tqdm as progress_bar
from zoneinfo import ZoneInfo
from google_drive_client import GoogleDriveClient

class Color:
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARK_CYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"

CONF_PATH = "zoom-recording-downloader.conf"

# Load configuration file and check for proper JSON syntax
try:
    with open(CONF_PATH, encoding="utf-8-sig") as json_file:
        CONF = json.loads(json_file.read())
except json.JSONDecodeError as e:
    print(f"{Color.RED}### Error parsing JSON in {CONF_PATH}: {e}")
    system.exit(1)
except FileNotFoundError:
    print(f"{Color.RED}### Configuration file {CONF_PATH} not found")
    system.exit(1)
except Exception as e:
    print(f"{Color.RED}### Unexpected error: {e}")
    system.exit(1)

def config(section, key, default=''):
    try:
        return CONF[section][key]
    except KeyError:
        if default == LookupError:
            print(f"{Color.RED}### No value provided for {section}:{key} in {CONF_PATH}")
            system.exit(1)
        else:
            return default

def normalize_user_statuses(raw_statuses):
    if isinstance(raw_statuses, str):
        candidates = [s.strip() for s in raw_statuses.split(",")]
    elif isinstance(raw_statuses, list):
        candidates = [str(s).strip() for s in raw_statuses]
    else:
        candidates = []

    allowed = {"active", "inactive", "pending"}
    normalized = [s.lower() for s in candidates if s and s.lower() in allowed]

    if not normalized:
        normalized = ["active"]

    # De-duplicate while preserving order
    seen = set()
    unique = []
    for status in normalized:
        if status not in seen:
            unique.append(status)
            seen.add(status)
    return unique

ACCOUNT_ID = config("OAuth", "account_id", LookupError)
CLIENT_ID = config("OAuth", "client_id", LookupError)
CLIENT_SECRET = config("OAuth", "client_secret", LookupError)

APP_VERSION = "3.1 (Google Drive Edition)"

API_ENDPOINT_USER_LIST = "https://api.zoom.us/v2/users"

RECORDING_START_YEAR = config("Recordings", "start_year", date.today().year)
RECORDING_START_MONTH = config("Recordings", "start_month", 1)
RECORDING_START_DAY = config("Recordings", "start_day", 1)
RECORDING_START_DATE = parser.parse(config("Recordings", "start_date", f"{RECORDING_START_YEAR}-{RECORDING_START_MONTH}-{RECORDING_START_DAY}")).replace(tzinfo=timezone.utc)
RECORDING_END_DATE = parser.parse(config("Recordings", "end_date", str(date.today()))).replace(tzinfo=timezone.utc)
DOWNLOAD_DIRECTORY = config("Storage", "download_dir", 'downloads')
COMPLETED_MEETING_IDS_LOG = config("Storage", "completed_log", 'completed-downloads.log')
COMPLETED_MEETING_IDS = set()

MEETING_TIMEZONE = ZoneInfo(config("Recordings", "timezone", 'UTC'))
MEETING_STRFTIME = config("Recordings", "strftime", '%Y.%m.%d - %I.%M %p UTC')
MEETING_FILENAME = config("Recordings", "filename", '{meeting_time} - {topic} - {rec_type} - {recording_id}.{file_extension}')
MEETING_FOLDER = config("Recordings", "folder", '{topic} - {meeting_time}')

# Google Drive configuration
GDRIVE_ENABLED = False
GDRIVE_CREDENTIALS_FILE = config("GoogleDrive", "credentials_file", "service-account.json")
GDRIVE_ROOT_FOLDER = config("GoogleDrive", "root_folder_name", "zoom-recording-downloader")
GDRIVE_RETRY_DELAY = int(config("GoogleDrive", "retry_delay", "5"))
GDRIVE_MAX_RETRIES = int(config("GoogleDrive", "max_retries", "3"))
GDRIVE_FAILED_LOG = config("GoogleDrive", "failed_log", "failed-uploads.log")

# User listing configuration
USERS_PAGE_SIZE = int(config("Users", "page_size", 300))
USER_STATUSES = normalize_user_statuses(config("Users", "statuses", ["active"]))

def setup_google_drive():
    """Initialize Google Drive client with OAuth authentication"""
    try:
        drive_client = GoogleDriveClient(CONF.get('GoogleDrive', {}))
        if not drive_client.authenticate():
            choice = input("Would you like to continue with local storage instead? (y/n): ")
            if choice.lower() != 'y':
                system.exit(1)
            return None

        if not drive_client.initialize_root_folder():
            print(f"{Color.RED}### Failed to create root folder in Google Drive{Color.END}")
            choice = input("Would you like to continue with local storage instead? (y/n): ")
            if choice.lower() != 'y':
                system.exit(1)
            return None

        return drive_client
    except Exception as e:
        print(f"{Color.RED}### Google Drive initialization failed: {str(e)}{Color.END}")
        choice = input("Would you like to continue with local storage instead? (y/n): ")
        if choice.lower() != 'y':
            system.exit(1)
        return None




def load_access_token():
    """ OAuth function, thanks to https://github.com/freelimiter
    """
    url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ACCOUNT_ID}"

    client_cred = f"{CLIENT_ID}:{CLIENT_SECRET}"
    client_cred_base64_string = base64.b64encode(client_cred.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {client_cred_base64_string}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = json.loads(requests.request("POST", url, headers=headers).text)

    global ACCESS_TOKEN
    global AUTHORIZATION_HEADER

    try:
        ACCESS_TOKEN = response["access_token"]
        AUTHORIZATION_HEADER = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

    except KeyError:
        print(f"{Color.RED}### The key 'access_token' wasn't found.{Color.END}")


def get_users(statuses, page_size):
    """ loop through pages and return all users for the given status values """
    all_users_by_id = {}

    for status in statuses:
        params = {
            "status": status,
            "page_size": page_size,
        }
        response = requests.get(url=API_ENDPOINT_USER_LIST, headers=AUTHORIZATION_HEADER, params=params)

        if not response.ok:
            print(response)
            print(
                f"{Color.RED}### Could not retrieve users with status '{status}'. Please make sure "
                f"that your access token is still valid{Color.END}"
            )
            system.exit(1)

        page_data = response.json()
        total_pages = int(page_data.get("page_count", 1))

        for page in range(1, total_pages + 1):
            params = {
                "status": status,
                "page_number": page,
                "page_size": page_size,
            }
            user_data = requests.get(url=API_ENDPOINT_USER_LIST, headers=AUTHORIZATION_HEADER, params=params).json()
            users = ([
                (
                    user.get("email", ""),
                    user.get("id", ""),
                    user.get("first_name", ""),  # Use .get() with a default value
                    user.get("last_name", ""),   # Use .get() with a default value
                    user.get("status", status)
                )
                for user in user_data.get("users", [])
                if user.get("id")
            ])

            for user in users:
                all_users_by_id[user[1]] = user

    return list(all_users_by_id.values())


def format_filename(params):
    file_extension = params["file_extension"].lower()
    recording = params["recording"]
    recording_id = params["recording_id"]
    recording_type = params["recording_type"]

    invalid_chars_pattern = r'[<>:"/\\|?*\x00-\x1F]'
    topic = regex.sub(invalid_chars_pattern, '', recording["topic"])
    rec_type = recording_type.replace("_", " ").title()
    meeting_time_utc = parser.parse(recording["start_time"]).replace(tzinfo=timezone.utc)
    meeting_time_local = meeting_time_utc.astimezone(MEETING_TIMEZONE)
    year = meeting_time_local.strftime("%Y")
    month = meeting_time_local.strftime("%m")
    day = meeting_time_local.strftime("%d")
    meeting_time = meeting_time_local.strftime(MEETING_STRFTIME)

    filename = MEETING_FILENAME.format(**locals())
    folder = MEETING_FOLDER.format(**locals())
    return (filename, folder)


def truncate_filename(filename, max_length=75):
    """
    Truncate filename to max_length characters, keeping the extension visible.
    If filename is longer than max_length, truncate in the middle with ellipses.
    
    Args:
        filename: The filename to truncate
        max_length: Maximum length including ellipses (default: 75)
    
    Returns:
        Truncated filename if longer than max_length, otherwise original filename
    """
    if len(filename) <= max_length:
        return filename
    
    # Find the extension (everything after the last dot)
    last_dot_index = filename.rfind('.')
    if last_dot_index == -1:
        # No extension found, treat entire filename as name
        extension = ""
        name_part = filename
    else:
        extension = filename[last_dot_index:]  # includes the dot
        name_part = filename[:last_dot_index]
    
    # Calculate available space for name parts: max_length - ellipses - extension
    ellipses = "..."
    available_space = max_length - len(ellipses) - len(extension)
    
    # If extension is too long, we can't fit it (shouldn't happen in practice)
    if available_space < 2:
        return filename[:max_length - 3] + "..."
    
    # Split available space equally between start and end
    start_length = available_space // 2
    end_length = available_space - start_length  # Handles odd numbers
    
    # Extract start and end parts
    start_part = name_part[:start_length]
    end_part = name_part[-end_length:] if end_length > 0 else ""
    
    # Combine: start + ellipses + end + extension
    return start_part + ellipses + end_part + extension


def get_downloads(recording):
    if not recording.get("recording_files"):
        raise Exception

    downloads = []
    for download in recording["recording_files"]:
        file_type = download["file_type"]
        file_extension = download["file_extension"]
        recording_id = download["id"]

        if file_type == "":
            recording_type = "incomplete"
        elif file_type != "TIMELINE":
            recording_type = download["recording_type"]
        else:
            recording_type = download["file_type"]

        # must append access token to download_url
        download_url = f"{download['download_url']}?access_token={ACCESS_TOKEN}"
        downloads.append((file_type, file_extension, download_url, recording_type, recording_id))

    return downloads


def get_recordings(email, page_size, rec_start_date, rec_end_date):
    return {
        "userId": email,
        "page_size": page_size,
        "from": rec_start_date,
        "to": rec_end_date
    }


def per_delta(start, end, delta):
    """ Generator used to create deltas for recording start and end dates
    """
    curr = start
    while curr < end:
        yield curr, min(curr + delta, end)
        curr += delta


def list_recordings(email):
    """ Start date now split into YEAR, MONTH, and DAY variables (Within 6 month range)
        then get recordings within that range
    """

    recordings = []

    for start, end in per_delta(RECORDING_START_DATE, RECORDING_END_DATE, timedelta(days=30)):
        post_data = get_recordings(email, 300, start, end)
        response = requests.get(
            url=f"https://api.zoom.us/v2/users/{email}/recordings",
            headers=AUTHORIZATION_HEADER,
            params=post_data
        )
        recordings_data = response.json()
        if "meetings" in recordings_data:
            recordings.extend(recordings_data["meetings"])
        else:
            print(f"No 'meetings' key found in response for {email} from {start} to {end}")

    return recordings


def download_recording(download_url, email, filename, folder_name):
    dl_dir = os.sep.join([DOWNLOAD_DIRECTORY, folder_name])
    sanitized_download_dir = path_validate.sanitize_filepath(dl_dir)
    sanitized_filename = path_validate.sanitize_filename(filename)
    full_filename = os.sep.join([sanitized_download_dir, sanitized_filename])

    os.makedirs(sanitized_download_dir, exist_ok=True)

    response = requests.get(download_url, stream=True)

    # total size in bytes.
    total_size = int(response.headers.get("content-length", 0))
    block_size = 32 * 1024  # 32 Kibibytes

    # create TQDM progress bar
    prog_bar = progress_bar.tqdm(dynamic_ncols=True, total=total_size, unit="iB", unit_scale=True)
    try:
        with open(full_filename, "wb") as fd:
            for chunk in response.iter_content(block_size):
                prog_bar.update(len(chunk))
                fd.write(chunk)  # write video chunk to disk
        prog_bar.close()

        return True

    except Exception as e:
        print(
            f"{Color.RED}### The video recording with filename '{filename}' for user with email "
            f"'{email}' could not be downloaded because {Color.END}'{e}'"
        )

        return False


def load_completed_meeting_ids():
    try:
        with open(COMPLETED_MEETING_IDS_LOG, 'r') as fd:
            [COMPLETED_MEETING_IDS.add(line.strip()) for line in fd]

    except FileNotFoundError:
        print(
            f"{Color.DARK_CYAN}Log file not found. Creating new log file: {Color.END}"
            f"{COMPLETED_MEETING_IDS_LOG}\n"
        )


def handle_graceful_shutdown(signal_received, frame):
    print(f"\n{Color.DARK_CYAN}SIGINT or CTRL-C detected. system.exiting gracefully.{Color.END}")

    system.exit(0)


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="Zoom Recording Downloader - Download and organize Zoom cloud recordings"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip downloading files that already exist in the output directory"
    )
    parser.add_argument(
        "--skip-users",
        nargs="+",
        metavar="EMAIL",
        default=[],
        help="List of user emails to skip (e.g., --skip-users user1@example.com user2@example.com)"
    )
    return parser.parse_args()


# ################################################################
# #                        MAIN                                  #
# ################################################################

def main():
    # Parse command-line arguments
    args = parse_arguments()

    # clear the screen buffer
    os.system('cls' if os.name == 'nt' else 'clear')

    # show the logo
    print(f"""
        {Color.DARK_CYAN}


                             ,*****************.
                          *************************
                        *****************************
                      *********************************
                     ******               ******* ******
                    *******                .**    ******
                    *******                       ******/
                    *******                       /******
                    ///////                 //    //////
                    ///////*              ./////.//////
                     ////////////////////////////////*
                       /////////////////////////////
                          /////////////////////////
                             ,/////////////////

                        Zoom Recording Downloader

                        V{APP_VERSION}

        {Color.END}
    """)

    # Storage choice prompt
    print("\nChoose download method:")
    print("1. Local Storage")
    print("2. Google Drive")
    choice = input("Enter choice (1-2): ")

    global GDRIVE_ENABLED
    GDRIVE_ENABLED = (choice == "2")

    drive_service = None
    if GDRIVE_ENABLED:
        drive_service = setup_google_drive()
        if not drive_service:
            GDRIVE_ENABLED = False

    load_access_token()
    load_completed_meeting_ids()

    print(f"{Color.BOLD}Getting user accounts...{Color.END}")
    users = get_users(USER_STATUSES, USERS_PAGE_SIZE)
    total_users = len(users)

    print(f"\n{Color.BOLD}Found {total_users} users:{Color.END}")
    for idx, (email, user_id, first_name, last_name, status) in enumerate(users, start=1):
        status_label = f" ({status})" if status else ""
        user_display = f"{first_name} {last_name} - {email}{status_label}" if first_name and last_name else f"{email}{status_label}"
        print(f"  {idx}. {user_display}")

    for user_idx, (email, user_id, first_name, last_name, status) in enumerate(users, start=1):
        # Skip users specified in --skip-users
        if email in args.skip_users:
            print(f"\n{Color.DARK_CYAN}Skipping user {user_idx}/{total_users}: {email}{Color.END}")
            continue

        status_label = f" ({status})" if status else ""
        userInfo = (
            f"{first_name} {last_name} - {email}{status_label}" if first_name and last_name else f"{email}{status_label}"
        )
        print(f"\n{Color.BOLD}[{user_idx}/{total_users}] Getting recording list for {userInfo}{Color.END}")

        recordings = list_recordings(user_id)
        total_count = len(recordings)
        print(f"==> Found {total_count} recordings")

        for index, recording in enumerate(recordings):
            try:
                recording_id = recording["uuid"]

                if recording_id in COMPLETED_MEETING_IDS:
                    print(
                        f"\n==> Skipping already downloaded recording {index + 1} of {total_count}"
                    )
                    continue

                downloads = get_downloads(recording)

            except Exception as e:
                print(
                    f"{Color.RED}### Failed to get download URLs for recording {index + 1} "
                    f"of {total_count} due to error: {str(e)}{Color.END}"
                )
                continue

            print(f"\n==> Processing recording {index + 1} of {total_count}")

            for file_type, file_extension, download_url, recording_type, recording_id in downloads:
                try:
                    params = {
                        "file_extension": file_extension,
                        "recording": recording,
                        "recording_id": recording_id,
                        "recording_type": recording_type
                    }
                    filename, folder_name = format_filename(params)

                    sanitized_download_dir = path_validate.sanitize_filepath(
                        os.sep.join([DOWNLOAD_DIRECTORY, folder_name])
                    )
                    sanitized_filename = path_validate.sanitize_filename(filename)
                    full_filename = os.sep.join([sanitized_download_dir, sanitized_filename])

                    # Skip if file already exists and --skip-existing flag is set
                    if args.skip_existing and os.path.exists(full_filename):
                        print(f"    > Skipping {truncate_filename(filename)} (already exists)")
                        continue

                    print(f"    > Downloading {truncate_filename(filename)}")

                    if download_recording(download_url, email, filename, folder_name):
                        if GDRIVE_ENABLED and drive_service:
                            print(f"    > Uploading to Google Drive...")
                            success = drive_service.upload_file(full_filename, folder_name, sanitized_filename)
                            if success and os.path.exists(full_filename):
                                os.remove(full_filename)
                                if not os.listdir(sanitized_download_dir):
                                    os.rmdir(sanitized_download_dir)

                except Exception as e:
                    print(
                        f"{Color.RED}### Failed to process file {file_type} "
                        f"for recording {index + 1} of {total_count} due to error: "
                        f"{str(e)}{Color.END}"
                    )
                    continue

            with open(COMPLETED_MEETING_IDS_LOG, "a") as fd:
                fd.write(f"{recording_id}\n")
                COMPLETED_MEETING_IDS.add(recording_id)


if __name__ == "__main__":
    # tell Python to shutdown gracefully when SIGINT is received
    signal.signal(signal.SIGINT, handle_graceful_shutdown)

    main()