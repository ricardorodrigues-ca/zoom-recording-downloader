#!/usr/bin/env python3

# Program Name: zoom-recording-downloader.py
# Description:  Zoom Recording Downloader is a cross-platform Python script
#               that uses Zoom's API (v2) to download and organize all
#               cloud recordings from a Zoom account onto local storage.
#               This Python script uses the JSON Web Token (JWT)
#               method of accessing the Zoom API
# Version:      2.0
# Created:      2020-04-26
# Author:       Ricardo Rodrigues
# Website:      https://github.com/ricardorodrigues-ca/zoom-recording-downloader
# Forked from https://gist.github.com/danaspiegel/c33004e52ffacb60c24215abf8301680

import os
import sys
import time
import requests
import itertools
from dateutil.parser import parse
from signal import signal, SIGINT
from sys import exit
# Import app environment variables
from appenv import JWT_TOKEN
# Import TQDM progress bar library
from tqdm import tqdm

# JWT_TOKEN now lives in appenv.py
ACCESS_TOKEN = 'Bearer ' + JWT_TOKEN
AUTHORIZATION_HEADER = { 'Authorization': ACCESS_TOKEN }

API_ENDPOINT_USER_LIST = 'https://api.zoom.us/v2/users'

RECORDING_START_DATE = '2020-01-01' # Start date in 'yyyy-mm-dd' format (within 6 month range)
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
    response = requests.get(url=API_ENDPOINT_USER_LIST, headers=AUTHORIZATION_HEADER)
    page_data = response.json()
    total_pages = int(page_data['page_count']) + 1

    # results will be appended to this list
    all_entries = []

    # loop through all pages and return user data
    for page in range(1, total_pages):
        url = API_ENDPOINT_USER_LIST + "?page_number=" + str(page)
        user_data = requests.get(url=url, headers=AUTHORIZATION_HEADER).json()
        user_ids = [(user['email'], user['id'], user['first_name'], user['last_name']) for user in user_data['users']]
        all_entries.extend(user_ids)
        data = all_entries
        page += 1
    return data


def format_filename(recording, file_type):
    uuid = recording['uuid']
    topic = recording['topic'].replace('/', '&')
    meeting_time = parse(recording['start_time'])

    return '{} - {} UTC - {}.{}'.format(
        meeting_time.strftime('%Y.%m.%d'), meeting_time.strftime('%I.%M %p'), topic, file_type.lower())


def get_downloads(recording):
    downloads = []
    for download in recording['recording_files']:
        file_type = download['file_type']
        download_url = download['download_url'] + "?access_token=" + JWT_TOKEN # must append JWT token to download_url
        downloads.append((file_type, download_url, ))
    return downloads


def list_recordings(email):
    post_data = get_credentials(email, 1, RECORDING_START_DATE)
    response = requests.get(url=API_ENDPOINT_RECORDING_LIST(email), headers=AUTHORIZATION_HEADER, params=post_data)
    recordings_data = response.json()
    total_records = recordings_data['total_records']
    page_count = recordings_data['page_count']
    next_page = recordings_data['next_page_token']

    if total_records == 0:
        return []

    if page_count <= 1:
        return recordings_data['meetings']

    recordings = recordings_data['meetings']

    # paginate through list of all recordings
    for i in range(1, page_count):  # start at page index 1 since we already have the first page
        post_data = { 'userId': email, 'from': RECORDING_START_DATE, 'next_page_token': next_page }
        response = requests.get(url=API_ENDPOINT_RECORDING_LIST(email), headers=AUTHORIZATION_HEADER, params=post_data)
        recordings_data = response.json()
        next_page = recordings_data['next_page_token'] # update with new next_page_token
        recordings.extend(recordings_data['meetings'])
    return recordings


def download_recording(download_url, email, filename):
    dl_dir = os.sep.join([DOWNLOAD_DIRECTORY, email])
    full_filename = os.sep.join([dl_dir, filename])
    os.makedirs(dl_dir, exist_ok=True)
    response = requests.get(download_url, stream=True)

    # total size in bytes.
    total_size = int(response.headers.get('content-length', 0))
    block_size = 32 * 1024 # 32 Kibibytes

    # create TQDM progress bar
    t = tqdm(total=total_size, unit='iB', unit_scale=True)
    try:
        with open(full_filename, 'wb') as fd:
        #with open(os.devnull, 'wb') as fd: # write to dev/null when testing
            for chunk in response.iter_content(block_size):
                t.update(len(chunk))
                fd.write(chunk) # write video chunk to disk
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
        print("Log file not found. Creating new log file: ", COMPLETED_MEETING_IDS_LOG)
        print('')


def handler(signal_received, frame):
    # handle cleanup here
    print('\nSIGINT or CTRL-C detected. Exiting gracefully.')
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

                                  Version 2.0
''')

    load_completed_meeting_ids()

    print(color.BOLD + "Getting user accounts..." + color.END)
    users = get_user_ids()

    for email, user_id, first_name, last_name in users:
        print(color.BOLD + "\nGetting recording list for {} {} ({})".format(first_name, last_name, email) + color.END)
        # wait n.n seconds so we don't breach the API rate limit
        #time.sleep(0.1)
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

            for file_type, download_url in downloads:
                filename = format_filename(recording, file_type)
                truncated_url = download_url[0:64] + "..." # truncate URL to 64 characters
                print("==> Downloading ({} of {}): {}: {}".format(index+1, total_count, meeting_id, truncated_url))
                success |= download_recording(download_url, email, filename)
                #success = True

            if success:
                # if successful, write the ID of this recording to the completed file
                with open(COMPLETED_MEETING_IDS_LOG, 'a') as log:
                    COMPLETED_MEETING_IDS.add(meeting_id)
                    log.write(meeting_id)
                    log.write('\n')
                    log.flush()

    print(color.BOLD + color.GREEN + "\n*** All done! ***" + color.END)
    save_location = os.path.abspath(DOWNLOAD_DIRECTORY)
    print(color.BLUE + "\nRecordings have been saved to: " + color.UNDERLINE + "{}".format(save_location) + color.END + "\n")

if __name__ == "__main__":
    # tell Python to run the handler() function when SIGINT is recieved
    signal(SIGINT, handler)

    main()
