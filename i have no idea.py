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

def get_user_info(headers, livename, stop_event=None):
    global userinfo, token
    while True:
        if stop_event and stop_event.is_set():
            fprint(f'Stopping user info thread for {livename}')
            break
    
        response = requests.get(f'https://api.twitch.tv/helix/users?login={livename}', headers=headers)
        if response.status_code in [200, 201]:
            userinfo[livename] = response.json()['data'][0]

            if not debug:
                sleep(1800)
        elif response.status_code == 401:
            token = get_token()
            headers['Authorization'] = f'Bearer {token}'
            continue
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
        return get_live_info(headers, livename)
    else:
        fprint(f'Error {response.status_code}')
        return None

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

            response = get_live_info(headers, livename)
            is_live = False

            if response and response.json()['data']:
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
            if not debug:
                sleep(5)
    except Exception as e:
        fprint(f"[red]check_live thread for {livename} crashed: {e}")

@bot.command()
async def adduser(ctx, username):
    if username in users:
        await ctx.send(f'{username} already exists')
        return
    users[username] = False
    live_status[username] = False
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
    user_threads[username] = [t1, t2]
    await ctx.send(f'{username} added')
    print('User added:', username)

@bot.command()
async def removeuser(ctx, username):
    if username in users:
        # Signal threads to stop
        if username in user_stop_events:
            user_stop_events[username].set()

        del users[username]

        if username in live_status:
            del live_status[username]

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
            price += f'{username}: {"Live :red_circle:" if live_status[username] == True else "Offline"}\n'
        
    embed = discord.Embed(title="Users being Checked:")
    embed.description = price if price else "No users being checked."
    embed.color = discord.Color.from_str("#884dc6")

    embed.set_author(name="Twitch Check Bot")
    await ctx.send(embed=embed)
    #await ctx.send(f'Users:\n{price}')

def thread_monitor():
    while True:
        sleep(10)
        for username in list(users.keys()):
            # Check if threads exist and are alive
            threads = user_threads.get(username, [])
            need_restart = False
            if len(threads) != 2:
                need_restart = True
            else:
                for t in threads:
                    if not t.is_alive():
                        need_restart = True
                        break
            if need_restart:
                fprint(f"[yellow]Restarting threads for {username}")
                stop_event = user_stop_events.get(username) or Event()
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

    for x in users:
        stop_event = Event()
        user_stop_events[x] = stop_event
        t1 = Thread(target=get_user_info, args=(headers, x, stop_event), name=f"{x}-userinfo")
        t2 = Thread(target=check_live, args=(headers, x, stop_event), name=f"{x}-checklive")
        t1.start()
        t2.start()
        user_threads[x] = [t1, t2]
        live_status[x] = False
    if not debug:
        bot.run(token=dcbot_token)
