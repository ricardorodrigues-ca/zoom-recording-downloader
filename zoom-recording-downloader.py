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

# Import json and base64 needed for Zoom OAuth
import json
import base64
# Import TQDM progress bar library
from tqdm import tqdm
# Import app environment variables
from appenv import JWT_TOKEN
from sys import exit
from signal import signal, SIGINT
from dateutil.parser import parse
import datetime
from datetime import date
from dateutil import relativedelta
from datetime import date, timedelta
from pathvalidate import sanitize_filepath, sanitize_filename
import itertools
import requests
import time
import sys
import os
APP_VERSION = "2.1"

# To get these 3 infos, create a 'Server-to-Server OAuth' on Zoom Developers web site. Set permissions in 'Scopes' for all the itens in account, meetings, recordings, users.
ACCOUNT_ID = ''
CLIENT_ID = ''
CLIENT_SECRET = ''

API_ENDPOINT_USER_LIST = 'https://api.zoom.us/v2/users'

# Start date now split into YEAR, MONTH, and DAY variables (Within 6 month range)
RECORDING_START_YEAR = 2022
RECORDING_START_MONTH = 1
RECORDING_START_DAY = 1
RECORDING_END_DATE = date.today()
# RECORDING_END_DATE = date(2021, 8, 1)
DOWNLOAD_DIRECTORY = 'downloads'
COMPLETED_MEETING_IDS_LOG = 'completed-downloads.log'
COMPLETED_MEETING_IDS = set()


# define class for text colouring and highlighting
class color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# New OAuth function, thanks to https://github.com/freelimiter
def load_access_token():

    url = "https://zoom.us/oauth/token?grant_type=account_credentials&account_id=" + ACCOUNT_ID

    client_cred = CLIENT_ID + ":" + CLIENT_SECRET
    client_cred_base64_string = base64.b64encode(client_cred.encode('utf-8')).decode('utf-8')

    headers = {
    'Authorization': 'Basic ' + client_cred_base64_string,
    'Content-Type': 'application/x-www-form-urlencoded'
    }

    response = requests.request("POST", url, headers=headers)

    jdata = json.loads(response.text)

    global ACCESS_TOKEN
    global AUTHORIZATION_HEADER

    try:
        ACCESS_TOKEN = jdata["access_token"]
        AUTHORIZATION_HEADER = {'Authorization': 'Bearer ' + ACCESS_TOKEN,
                            'Content-Type': 'application/json'}

    except KeyError:
        print("The key 'access_token' wasn't found.")

def API_ENDPOINT_RECORDING_LIST(email):
    API_ENDPOINT = 'https://api.zoom.us/v2/users/' + email + '/recordings'
    return API_ENDPOINT


def get_credentials(host_id, page_number, rec_start_date):
    return {
        'host_id': host_id,
        'page_number': page_number,
        'from': rec_start_date,
    }


def get_user_ids():
    # get total page count, convert to integer, increment by 1
    response = requests.get(url=API_ENDPOINT_USER_LIST,
                            headers=AUTHORIZATION_HEADER)
    if not response.ok:
        print(response)
        print('Is your JWT still valid?')
        exit(1)
    page_data = response.json()
    total_pages = int(page_data['page_count']) + 1

    # results will be appended to this list
    all_entries = []

    # loop through all pages and return user data
    for page in range(1, total_pages):
        url = API_ENDPOINT_USER_LIST + "?page_number=" + str(page)
        user_data = requests.get(url=url, headers=AUTHORIZATION_HEADER).json()
        user_ids = [(user['email'], user['id'], user['first_name'],
                     user['last_name']) for user in user_data['users']]
        all_entries.extend(user_ids)
        data = all_entries
        page += 1
    return data


def format_filename(recording, file_type, file_extension, recording_type, recording_id):
    uuid = recording['uuid']
    topic = recording['topic'].replace('/', '&')
    rec_type = recording_type.replace("_", " ").title()
    meeting_time = parse(recording['start_time']).strftime('%Y.%m.%d - %I.%M %p UTC')
    return '{} - {} - {}.{}'.format(
        meeting_time, topic+" - "+rec_type, recording_id, file_extension.lower()),'{} - {}'.format(topic, meeting_time)


def get_downloads(recording):
    downloads = []
    for download in recording['recording_files']:
        file_type = download['file_type']
        file_extension = download['file_extension']
        recording_id = download['id']
        if file_type == "":
            recording_type = 'incomplete'
            #print("\download is: {}".format(download))
        elif file_type != "TIMELINE":
            recording_type = download['recording_type']
        else:
            recording_type = download['file_type']
        # must append JWT token to download_url
        download_url = download['download_url'] + "?access_token=" + JWT_TOKEN
        downloads.append((file_type, file_extension, download_url, recording_type, recording_id))
    return downloads


def get_recordings(email, page_size, rec_start_date, rec_end_date):
    return {
        'userId':       email,
        'page_size':    page_size,
        'from':         rec_start_date,
        'to':           rec_end_date
    }


# Generator used to create deltas for recording start and end dates
def perdelta(start, end, delta):
    curr = start
    while curr < end:
        yield curr, min(curr + delta, end)
        curr += delta


def list_recordings(email):
    recordings = []

    for start, end in perdelta(date(RECORDING_START_YEAR, RECORDING_START_MONTH, RECORDING_START_DAY), RECORDING_END_DATE, timedelta(days=30)):
        post_data = get_recordings(email, 300, start, end)
        response = requests.get(url=API_ENDPOINT_RECORDING_LIST(
            email), headers=AUTHORIZATION_HEADER, params=post_data)
        recordings_data = response.json()
        recordings.extend(recordings_data['meetings'])
    return recordings


def download_recording(download_url, email, filename, foldername):
    dl_dir = os.sep.join([DOWNLOAD_DIRECTORY, foldername])
    dl_dir = sanitize_filepath(dl_dir)
    filename = sanitize_filename(filename)
    full_filename = os.sep.join([dl_dir, filename])
    os.makedirs(dl_dir, exist_ok=True)
    response = requests.get(download_url, stream=True)

    # total size in bytes.
    total_size = int(response.headers.get('content-length', 0))
    block_size = 32 * 1024  # 32 Kibibytes

    # create TQDM progress bar
    t = tqdm(total=total_size, unit='iB', unit_scale=True)
    try:
        with open(full_filename, 'wb') as fd:
            # with open(os.devnull, 'wb') as fd:  # write to dev/null when testing
            for chunk in response.iter_content(block_size):
                t.update(len(chunk))
                fd.write(chunk)  # write video chunk to disk
        t.close()
        return True
    except Exception as e:
        # if there was some exception, print the error and return False
        print(e)
        return False


def load_completed_meeting_ids():
    try:
        with open(COMPLETED_MEETING_IDS_LOG, 'r') as fd:
            for line in fd:
                COMPLETED_MEETING_IDS.add(line.strip())
    except FileNotFoundError:
        print("Log file not found. Creating new log file: ",
              COMPLETED_MEETING_IDS_LOG)
        print()


def handler(signal_received, frame):
    # handle cleanup here
    print(color.RED + "\nSIGINT or CTRL-C detected. Exiting gracefully." + color.END)
    exit(0)


# ################################################################
# #                        MAIN                                  #
# ################################################################

def main():

    # clear the screen buffer
    os.system('cls' if os.name == 'nt' else 'clear')

    # show the logo
    print('''

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

                                  Version {}
'''.format(APP_VERSION))

    # new OAuth authentication
    load_access_token()
    
    load_completed_meeting_ids()

    print(color.BOLD + "Getting user accounts..." + color.END)
    users = get_user_ids()

    for email, user_id, first_name, last_name in users:
        print(color.BOLD + "\nGetting recording list for {} {} ({})".format(first_name,
                                                                            last_name, email) + color.END)
        # wait n.n seconds so we don't breach the API rate limit
        # time.sleep(0.1)
        recordings = list_recordings(user_id)
        total_count = len(recordings)
        print("==> Found {} recordings".format(total_count))

        for index, recording in enumerate(recordings):
            success = False
            meeting_id = recording['uuid']
            if meeting_id in COMPLETED_MEETING_IDS:
                print("==> Skipping already downloaded meeting: {}".format(meeting_id))
                continue

            downloads = get_downloads(recording)
            for file_type, file_extension, download_url, recording_type, recording_id in downloads:
                if recording_type != 'incomplete':
                    filename, foldername = format_filename(
                        recording, file_type, file_extension, recording_type, recording_id)
                    # truncate URL to 64 characters
                    truncated_url = download_url[0:64] + "..."
                    print("==> Downloading ({} of {}) as {}: {}: {}".format(
                        index+1, total_count, recording_type, recording_id, truncated_url))
                    success |= download_recording(download_url, email, filename, foldername)
                    #success = True
                else:
                    print("### Incomplete Recording ({} of {}) for {}".format(index+1, total_count, recording_id))
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
    print(color.BLUE + "\nRecordings have been saved to: " +
          color.UNDERLINE + "{}".format(save_location) + color.END + "\n")


if __name__ == "__main__":
    # tell Python to run the handler() function when SIGINT is recieved
    signal(SIGINT, handler)

    main()
