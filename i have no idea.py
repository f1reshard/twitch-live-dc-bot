import requests
from rich import print as fprint
from discord_webhook import DiscordWebhook
from threading import Thread
from time import sleep

debug = False

client_id = 'ofxw53j2gjd5vb7utuv9uj3vonq4xk'
client_secret = 'sks9eq2ah11q82r4izvhiehohx5dq4'

token = None
userinfo = {}

users = {
    "nami_sleep": False,
    "notsosecureaccount": False,
    "liightlie": False
    }

def get_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    return response.json()['access_token']

def get_user_info(headers, livename):
    global userinfo, token
    while True:
        response = requests.get(f'https://api.twitch.tv/helix/users?login={livename}', headers=headers)
        if response.status_code in [200, 201]:
            userinfo[livename] = response.json()['data'][0]

            if not debug:
                sleep(1800)
        elif response.status_code == 401:
            token = get_token()
            headers['Authorization'] = f'Bearer {token}'
            get_user_info(headers, livename)
        else:
            fprint(f'Error {response.status_code}')
        


def get_live_info(headers, livename):
    global token

    response = requests.get(f'https://api.twitch.tv/helix/streams?user_login={livename}', headers=headers)
    if response.status_code in [200, 201]:
        return response
    
    elif response.status_code == 401:
        token = get_token()
        headers['Authorization'] = f'Bearer {token}'
        get_live_info(headers, livename)
    else:
        fprint(f'Error {response.status_code}')
        return None

def send_discord_embed(livename, islive):
    if islive:
        content = f"<@267440142124449794> {userinfo[livename]['display_name']} is [live!](https://twitch.tv/{livename})"
    else:
        content = f"{userinfo[livename]['display_name']} is now offline..."

    webhook = DiscordWebhook(
        url='https://discord.com/api/webhooks/1375661361375215727/B8eCmX5StH1YCaK2cCg0ikXHyvQSZGjlsM8Jxti_XIoiZEM2g70-bY14--OnIuJ8IhV7',
        content=content
    )
    webhook.execute()

def check_live(headers, livename):
    while True:
        response = get_live_info(headers, livename)
        if response and response.json()['data']:
            if response.json()['data'][0]['type'] == 'live':
                fprint(f"{livename} is live")
                if not users[livename]:
                    send_discord_embed(livename, True)
                    users[livename] = True
            else:
                fprint(f"{livename} is not live")
        else:
            fprint(f"{livename} is offline")
            if users[livename]:
                send_discord_embed(livename, False)
                users[livename] = False

        if not debug:
            sleep(5)

if __name__ == "__main__":
    token = get_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Client-Id': client_id,
    }

    for x in users:
        Thread(target=get_user_info, args=(headers, x)).start()
        Thread(target=check_live, args=(headers, x)).start()
