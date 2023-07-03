# zoom-recording-downloader

[![Python 3.6](https://img.shields.io/badge/python-3.6%20%2B-blue.svg)](https://www.python.org/) [![License](https://img.shields.io/badge/license-MIT-brown.svg)](https://raw.githubusercontent.com/ricardorodrigues-ca/zoom-recording-downloader/master/LICENSE)

**Zoom Recording Downloader** is a cross-platform Python script that uses Zoom's API (v2) to download and organize all cloud recordings from a Zoom account onto local storage.

## Screenshot ##
![screenshot](screenshot.png)

## Installation ##

_Attention: You will need [Python 3.6](https://www.python.org/downloads/) or greater_

```sh
$ git clone https://github.com/ricardorodrigues-ca/zoom-recording-downloader
$ cd zoom-recording-downloader
$ pip3 install -r requirements.txt
```

## Usage ##

_Attention: You will need a [Zoom Developer account](https://marketplace.zoom.us/) in order to create a [Server-to-Server OAuth app](https://developers.zoom.us/docs/internal-apps) with the required credentials_

1. Create a [server-to-server OAuth app](https://marketplace.zoom.us/user/build), set up your app and collect your credentials (`Account ID`, `Client ID`, `Client Secret`). For questions on this, [reference the docs](https://developers.zoom.us/docs/internal-apps/create/) on creating a server-to-server app. Make sure you activate the app. Follow Zoom's [set up documentation](https://marketplace.zoom.us/docs/guides/build/server-to-server-oauth-app/) or [this video](https://www.youtube.com/watch?v=OkBE7CHVzho) for a more complete walk through.

2. Add the necessary scopes to your app. In your app's _Scopes_ tab, add the following scopes: `account:master`, `account:read:admin`, `account:write:admin`, `information_barriers:read:admin`, `information_barriers:read:master`, `information_barriers:write:admin`, `information_barriers:write:master`, `meeting:master`, `meeting:read:admin`, `meeting:read:admin:sip_dialing`, `meeting:write:admin`, `meeting_token:read:admin:live_streaming`, `meeting_token:read:admin:local_archiving`, `meeting_token:read:admin:local_recording`, `recording:master`, `recording:read:admin`, `recording:write:admin`, `user:master`, `user:read:admin`, `user:write:admin`.

3. Copy **zoom-recording-downloader.conf.template** to a new file named **zoom-recording-downloader.conf** and fill in your Server-to-Server OAuth app credentials:
```
      {
	      "OAuth": {
		      "account_id": "<ACCOUNT_ID>",
		      "client_id": "<CLIENT_ID>",
		      "client_secret": "<CLIENT_SECRET>"
	      }
      }
```

4. Add environment variables. Open the **zoom-recording-downloader.py** file using your editor of choice and fill in the following variables to reflect your environment:

- Specify the folder name where the recordings will be downloaded (default is 'downloads')

      DOWNLOAD_DIRECTORY = 'downloads'

- Specify the name of the log file that will store the ID's of downloaded recordings (default is 'completed-downloads.log')

      COMPLETED_MEETING_IDS_LOG = 'completed-downloads.log'

Run command:

```sh
python3 zoom-recording-downloader.py
```
