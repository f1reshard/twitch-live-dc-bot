import requests
from rich import print as fprint
from discord_webhook import DiscordWebhook
import discord
from discord.ext import commands
from threading import Thread, Event, enumerate
from time import sleep
import os
from dotenv import load_dotenv
from ast import literal_eval
import threading
from requests.exceptions import RequestException
from datetime import datetime
from discord import Embed


load_dotenv(dotenv_path='twitch_clients.env')
debug = False
client_id = os.getenv('client_id')# twitch bot
client_secret = os.getenv('client_secret') # twitch bot
dcbot_token = os.getenv('dcbot_token')
userinfo = {}

with open('users.txt','r') as q:
    users = literal_eval(q.read())

# Track threads and stop events per user
user_threads = {}
user_stop_events = {}
# Track live status in memory only
live_status = {k: False for k in users}
current_titles = {k: "" for k in users}

# Add a lock for thread-safe operations
thread_lock = threading.Lock()

# discord bot logic ---
bot = commands.Bot(command_prefix='@',intents=discord.Intents.all())

@bot.event
async def on_ready():
    print('ready')


def get_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    return response.json()['access_token']

def get_user_info(headers, livename, stop_event=None, skip_sleep=False):
    global userinfo, token
    while True:
        if stop_event and stop_event.is_set():
            fprint(f'Stopping user info thread for {livename}')
            break
    
        response = requests.get(f'https://api.twitch.tv/helix/users?login={livename}', headers=headers)
        if response.status_code in [200, 201]:
            userinfo[livename] = response.json()['data'][0]
            if not debug and skip_sleep == False:
                sleep(1800)
            if skip_sleep:
                break

        elif response.status_code == 401:
            token = get_token()
            headers['Authorization'] = f'Bearer {token}'
            continue
        else:
            fprint(f'Error {response.status_code}')

def get_live_info(headers, livename, apicall):
    global token
    try:
        response = requests.get(f'https://api.twitch.tv/helix/{apicall}', headers=headers)
        if response.status_code in [200, 201]:
            return response

        elif response.status_code == 401:
            token = get_token()
            headers['Authorization'] = f'Bearer {token}'
            return get_live_info(headers, livename)
        else:
            fprint(f'Error {response.status_code}')
            return 'error'
    except RequestException as e:
        fprint(f'Error in get_live_info: {e}')
        return 'error'

def send_discord_embed(livename, islive):

    while livename not in userinfo:
        fprint(f"Waiting for user info for {livename}...")
        sleep(1)

    if islive:
        content = f"<@267440142124449794> {userinfo[livename]['display_name']} is [live!](https://twitch.tv/{livename})"
    else:
        content = f"{userinfo[livename]['display_name']} is now offline..."

    webhook = DiscordWebhook(
        url=os.getenv('webhook_url'),
        content=content
    )
    webhook.execute()

def check_live(headers, livename, stop_event=None):
    global live_status
    try:
        while True:
            if stop_event and stop_event.is_set():
                webhook = DiscordWebhook(
                    url=os.getenv('webhook_url'),
                    content='Stopping live check thread for ' + livename
                )
                webhook.execute()
                break

            #####################################
            response = get_live_info(headers, livename, f'streams?user_login={livename}')
            is_live = False

            if response == 'error':
                continue

            elif response and response.json()['data']:
                if response.json()['data'][0]['type'] == 'live':
                    is_live = True

            if is_live:
                fprint(f"{livename} is live")
                if livename not in live_status or not live_status[livename]:            
                    send_discord_embed(livename, True)

            else:
                fprint(f"{livename} is offline")
                if livename in live_status and live_status[livename]:
                    send_discord_embed(livename, False)

            live_status[livename] = is_live
            ######################################

            titleupdate = stream_title(livename, headers)

            if titleupdate != 'error' and titleupdate != current_titles[livename]:
                fprint(f"[blue]{livename} updated stream title to: {titleupdate}[/blue]")
                current_titles[livename] = titleupdate
            
                embed = {
                "author": {
                    "name": f"{userinfo[livename]['display_name']}",
                    "icon_url": f"{userinfo[livename]['profile_image_url']}",
                    "url": f"https://twitch.tv/{livename}"
                },
                "title": "Title Change",
                "fields": [
                    {
                    "name": f"{titleupdate}",
                    "value": "\u200b",
                    "inline": False
                    }
                ],
                "color": 0x359e69,
                "footer": {
                    "text": "Time"
                },
                "timestamp": datetime.utcnow().isoformat()}

                webhook = DiscordWebhook(
                    url=os.getenv('webhook_url'),
                )
                webhook.add_embed(embed)
                webhook.execute()



            if not debug:
                sleep(5)
    except Exception as e:
        fprint(f"[red]check_live thread for {livename} crashed: {e}")

def stream_title(livename, headers):
    try:
        if livename not in userinfo:
            get_user_info(headers, livename, skip_sleep=True)

        response = requests.get(f'https://api.twitch.tv/helix/channels?broadcaster_id={userinfo[livename]["id"]}', headers=headers)

        if response.status_code in [200, 201]:
            usertitle = response.json()['data'][0]['title']
            return usertitle
        elif response.status_code == 401:
            token = get_token()
            headers['Authorization'] = f'Bearer {token}'
            return stream_title(livename, headers)
        
        elif response.status_code == 429:
            fprint('[red]Rate limited when fetching stream title')
            sleep(1)
            return stream_title(livename, headers)
        
        else:
            fprint(f'Error {response.status_code} in stream_title')
            return 'error'

    except Exception as e:
        fprint(f'Error in stream_title: {e}')
        return 'error'

@bot.command()
async def adduser(ctx, username):
    global headers
    with thread_lock:
        if username in users:
            await ctx.send(f'{username} already exists')
            return
        users[username] = False
        live_status[username] = False
        current_titles[username] = stream_title(username, headers)
        with open('users.txt','w') as q:
            q.write(str(users))
        # Create stop event and threads for new user
        stop_event = Event()
        user_stop_events[username] = stop_event
        headers = {
            'Authorization': f'Bearer {get_token()}',
            'Client-Id': client_id,
        }
        userinfo_thread = Thread(target=get_user_info, args=(headers, username, stop_event), name=f"{username}-userinfo")
        checklive_thread = Thread(target=check_live, args=(headers, username, stop_event), name=f"{username}-checklive")
        userinfo_thread.start()
        checklive_thread.start()
        user_threads[username] = [userinfo_thread, checklive_thread]
    await ctx.send(f'{username} added')
    print('User added:', username)

@bot.command()
async def removeuser(ctx, username):
    with thread_lock:
        if username in users:
            # Signal threads to stop
            if username in user_stop_events:
                user_stop_events[username].set()

            del users[username]

            if username in live_status:
                del live_status[username]
            if username in user_threads:
                del user_threads[username]
            if username in user_stop_events:
                del user_stop_events[username]
            if username in current_titles:
                del current_titles[username]

            with open('users.txt','w') as q:
                q.write(str(users))

            await ctx.send(f'{username} removed')
        else:
            await ctx.send(f'{username} not found')

@bot.command()
async def listusers(ctx):
    price = ''
    for x in enumerate():
        if '-checklive' in x.name:
            username = x.name.removesuffix("-checklive")
            price += f'{username}: {"Live :red_circle:" if live_status.get(username) else "Offline"}\n'
        
    embed = discord.Embed(title="Users being Checked:")
    embed.description = price if price else "No users being checked."
    embed.color = discord.Color.from_str("#884dc6")

    embed.set_author(name="Twitch Check Bot")
    await ctx.send(embed=embed)
    #await ctx.send(f'Users:\n{price}')

@bot.command()
async def listthreads(ctx):
    threads_info = []
    for t in enumerate():
        if '-checklive' in t.name or '-userinfo' in t.name or 1 == 1:
            status = "Alive" if t.is_alive() else "Dead"
            threads_info.append(f"{t.name}: {status}")
    
    if not threads_info:
        threads_info.append("No active threads found.")

    embed = discord.Embed(title="Active Threads")
    embed.description = "\n".join(threads_info)
    embed.color = discord.Color.from_str("#884dc6")

    embed.set_author(name="Twitch Check Bot")
    await ctx.send(embed=embed)

def thread_monitor():
    while True:
        sleep(10)
        with thread_lock:
            for username in list(users.keys()):
                threads = user_threads.get(username, [])
                # If any thread is dead or missing, restart both
                if len(threads) != 2 or any(not t.is_alive() for t in threads):
                    fprint(f"[yellow]Restarting threads for {username}")
                    # Signal old threads to stop
                    if username in user_stop_events:
                        user_stop_events[username].set()
                    # Optionally join old threads (not strictly required)
                    for t in threads:
                        if t.is_alive():
                            t.join(timeout=1)
                    # Create new stop event and threads
                    stop_event = Event()
                    user_stop_events[username] = stop_event
                    headers = {
                        'Authorization': f'Bearer {get_token()}',
                        'Client-Id': client_id,
                    }
                    t1 = Thread(target=get_user_info, args=(headers, username, stop_event), name=f"{username}-userinfo")
                    t2 = Thread(target=check_live, args=(headers, username, stop_event), name=f"{username}-checklive")
                    t1.start()
                    t2.start()
                    user_threads[username] = [t1, t2]
         # Check every 10 seconds

# Start the monitor thread
monitor_thread = threading.Thread(target=thread_monitor, name="ThreadMonitor", daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    token = get_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Client-Id': client_id,
    }

    with thread_lock:
        for x in users:
            stop_event = Event()
            user_stop_events[x] = stop_event
            t1 = Thread(target=get_user_info, args=(headers, x, stop_event), name=f"{x}-userinfo")
            t2 = Thread(target=check_live, args=(headers, x, stop_event), name=f"{x}-checklive")
            t1.start()
            t2.start()
            user_threads[x] = [t1, t2]
            live_status[x] = False
            current_titles[x] = stream_title(x, headers)
    if not debug:
        bot.run(token=dcbot_token)
