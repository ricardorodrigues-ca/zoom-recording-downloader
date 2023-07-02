#!/usr/bin/env python3

# Program Name: zoom-recording-downloader.py
# Description:  Zoom Recording Downloader is a cross-platform Python script
#               that uses Zoom's API (v2) to download and organize all
#               cloud recordings from a Zoom account onto local storage.
#               This Python script uses the JSON Web Token (JWT)
#               method of accessing the Zoom API
# Created:      2020-04-26
# Author:       Ricardo Rodrigues
# Website:      https://github.com/ricardorodrigues-ca/zoom-recording-downloader
# Forked from:  https://gist.github.com/danaspiegel/c33004e52ffacb60c24215abf8301680

from signal import signal, SIGINT
import base64
import json
import os
import sys as system

# installed libraries
import datetime
import dateutil.parser as parser
import pathvalidate as path_validate
import requests
import tqdm as progress_bar

CONF_PATH = "zoom-recording-downloader.conf"
with open(CONF_PATH, encoding="utf-8-sig") as json_file:
    CONF = json.loads(json_file.read())

ACCOUNT_ID = CONF["account_id"]
CLIENT_ID = CONF["client_id"]
CLIENT_SECRET = CONF["client_secret"]

APP_VERSION = "3.0 (OAuth)"
API_ENDPOINT_USER_LIST = 'https://api.zoom.us/v2/users'

# Start date now split into YEAR, MONTH, and DAY variables (Within 6 month range)
RECORDING_START_YEAR = 2023
RECORDING_START_MONTH = 1
RECORDING_START_DAY = 1
RECORDING_END_DATE = datetime.date.today()
DOWNLOAD_DIRECTORY = 'downloads'
COMPLETED_MEETING_IDS_LOG = 'completed-downloads.log'
COMPLETED_MEETING_IDS = set()


# define class for text colouring and highlighting
class color:
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

    response = requests.request("POST", url, headers=headers)

    jdata = json.loads(response.text)

    global ACCESS_TOKEN
    global AUTHORIZATION_HEADER

    try:
        ACCESS_TOKEN = jdata["access_token"]
        AUTHORIZATION_HEADER = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

    except KeyError:
        print("The key 'access_token' wasn't found.")


def get_credentials(host_id, page_number, rec_start_date):
    return {
        "host_id": host_id,
        "page_number": page_number,
        "from": rec_start_date,
    }


def get_user_ids():
    # get total page count, convert to integer, increment by 1
    response = requests.get(url=API_ENDPOINT_USER_LIST, headers=AUTHORIZATION_HEADER)

    if not response.ok:
        print(response)
        print("Is your access token still valid?")
        system.exit(1)

    page_data = response.json()
    total_pages = int(page_data["page_count"]) + 1

    # results will be appended to this list
    all_entries = []

    # loop through all pages and return user data
    for page in range(1, total_pages):
        url = f"{API_ENDPOINT_USER_LIST}?page_number={str(page)}"
        user_data = requests.get(url=url, headers=AUTHORIZATION_HEADER).json()
        user_ids = ([
            (
                user["email"],
                user["id"],
                user["first_name"],
                user["last_name"]
            )
            for user in user_data["users"]
        ])

        all_entries.extend(user_ids)
        data = all_entries
        page += 1

    return data


def format_filename(params):
    file_extension = params["file_extension"]
    recording = params["recording"]
    recording_id = params["recording_id"]
    recording_type = params["recording_type"]

    topic = recording["topic"].replace("/", "&")
    rec_type = recording_type.replace("_", " ").title()
    meeting_time = parser.parse(recording["start_time"]).strftime("%Y.%m.%d - %I.%M %p UTC")

    return (
        f"{meeting_time} - {topic} - {rec_type} - {recording_id}.{file_extension.lower()}",
        f"{topic} - {topic}"
    )


def get_downloads(recording):
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
    recordings = []

    PER_DELTA = (
        per_delta(
            datetime.date(
                RECORDING_START_YEAR,
                RECORDING_START_MONTH,
                RECORDING_START_DAY
            ),
            RECORDING_END_DATE,
            datetime.timedelta(days=30)
        )
    )

    for start, end in PER_DELTA:
        post_data = get_recordings(email, 300, start, end)
        response = requests.get(
            url=f"https://api.zoom.us/v2/users/{email}/recordings",
            headers=AUTHORIZATION_HEADER, params=post_data
        )
        recordings_data = response.json()
        recordings.extend(recordings_data["meetings"])

    return recordings


def download_recording(download_url, email, filename, foldername):
    dl_dir = os.sep.join([DOWNLOAD_DIRECTORY, foldername])
    sanitized_download_dir = path_validate.sanitize_filepath(dl_dir)
    sanitized_filename = path_validate.sanitize_filename(filename)
    full_filename = os.sep.join([sanitized_download_dir, sanitized_filename])

    os.makedirs(sanitized_download_dir, exist_ok=True)

    response = requests.get(download_url, stream=True)

    # total size in bytes.
    total_size = int(response.headers.get("content-length", 0))
    block_size = 32 * 1024  # 32 Kibibytes

    # create TQDM progress bar
    prog_bar = progress_bar.tqdm(total=total_size, unit="iB", unit_scale=True)
    try:
        with open(full_filename, "wb") as fd:
            for chunk in response.iter_content(block_size):
                prog_bar.update(len(chunk))
                fd.write(chunk)  # write video chunk to disk
        prog_bar.close()

        return True

    except Exception as e:
        print(
            f"the video recording for user with email '{email}' could not be downloaded "
            f"because '{e}'"
        )

        return False


def load_completed_meeting_ids():
    try:
        with open(COMPLETED_MEETING_IDS_LOG, 'r') as fd:
            [COMPLETED_MEETING_IDS.add(line.strip()) for line in fd]

    except FileNotFoundError:
        print("Log file not found. Creating new log file: ", COMPLETED_MEETING_IDS_LOG)
        print()


def handle_graceful_shutdown():
    print(color.RED + "\nSIGINT or CTRL-C detected. system.exiting gracefully." + color.END)

    system.exit(0)


# ################################################################
# #                        MAIN                                  #
# ################################################################

def main():
    # clear the screen buffer
    os.system('cls' if os.name == 'nt' else 'clear')

    # show the logo
    print(
        f"""

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

                            Version {APP_VERSION}
        """
    )

    load_access_token()

    load_completed_meeting_ids()

    print(color.BOLD + "Getting user accounts..." + color.END)
    users = get_user_ids()

    for email, user_id, first_name, last_name in users:
        print(color.BOLD + f"\nGetting recording list for {first_name} {last_name} - ({email})")

        recordings = list_recordings(user_id)
        total_count = len(recordings)
        print(f"==> Found {total_count} recordings")

        for index, recording in enumerate(recordings):
            success = False
            meeting_id = recording["uuid"]
            if meeting_id in COMPLETED_MEETING_IDS:
                print(f"==> Skipping already downloaded meeting: {meeting_id}")

                continue

            downloads = get_downloads(recording)
            for file_extension, download_url, recording_type, recording_id in downloads:
                if recording_type != 'incomplete':
                    filename, foldername = (
                        format_filename({
                            "recording": recording,
                            "file_extension": file_extension,
                            "recording_type": recording_type,
                            "recording_id": recording_id
                        })
                    )

                    # truncate URL to 64 characters
                    truncated_url = download_url[0:64] + "..."
                    print(
                        f"==> Downloading ({index + 1} of {total_count}) as {recording_type}: "
                        f"{recording_id}: {truncated_url}"
                    )
                    success |= download_recording(download_url, email, filename, foldername)

                else:
                    print(
                        f"### Incomplete Recording ({index+1} of {total_count}) for {recording_id}"
                    )
                    success = False

            if success:
                # if successful, write the ID of this recording to the completed file
                with open(COMPLETED_MEETING_IDS_LOG, 'a') as log:
                    COMPLETED_MEETING_IDS.add(meeting_id)
                    log.write(meeting_id)
                    log.write('\n')
                    log.flush()

    print(color.BOLD + color.GREEN + "\n*** All done! ***" + color.END)
    save_location = os.path.abspath(DOWNLOAD_DIRECTORY)
    print(
        color.BLUE +
        "\nRecordings have been saved to: " +
        color.UNDERLINE +
        f"{save_location}" +
        color.END +
        "\n"
    )


if __name__ == "__main__":
    # tell Python to shutdown gracefully when SIGINT is received
    signal(SIGINT, handle_graceful_shutdown)

    main()
