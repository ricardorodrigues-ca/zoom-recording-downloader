# zoom-recording-downloader

[![Python 3.6](https://img.shields.io/badge/python-3.6%20%2B-blue.svg)](https://www.python.org/) [![License](https://img.shields.io/badge/license-MIT-brown.svg)](https://raw.githubusercontent.com/ricardorodrigues-ca/zoom-recording-downloader/master/LICENSE.md)

**Zoom Recording Downloader** is a cross-platform Python script that uses Zoom's API (v2) to download and organize all cloud recordings from a Zoom account onto local storage.

## Screenshot ##
![screenshot](screenshot.png)

## Installation ##

_Attention: You will need Python version 3.6 or greater_

```sh 
$ git clone https://github.com/ricardorodrigues-ca/zoom-recording-downloader
$ cd zoom-recording-downloader
$ pip3 install -r requirements.txt
```

## Usage ##

_Attention: You will need a Zoom Developer account, and a JWT app for the token_

Open the **zoom-recording-downloader.py** file using your favourite text editor or IDE, and modify the following variables to reflect your account:
    
- Set the JSON Web Token of your JWT app here

      JWT_TOKEN = 'your_token_goes_here'

- Set this variable to the earliest recording date you wish to download (default = 2020-01-01)
    
      RECORDING_START_DATE = '2020-01-01'
    
- Set this variable to the total number of users in your Zoom account (default = 1000)

      TOTAL_USERS = 1000

- Specify the folder name where recordings will be downloaded to (default = downloads)
    
      DOWNLOAD_DIRECTORY = 'downloads'
    
- Specify the file name of the log file that will store the ID's of the downloaded recordings (default = completed_downloads.log)

      COMPLETED_MEETING_IDS_LOG = 'completed-downloads.log'

Run command:

    python3 zoom-recording-downloader.py

