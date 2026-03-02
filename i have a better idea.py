import requests
import json
from rich import print as fprint
from discord_webhook import DiscordWebhook
import discord
from discord.ext import commands
from threading import Thread
from time import sleep as eepy
import os
from dotenv import load_dotenv
from requests.exceptions import RequestException
from datetime import datetime
from random import randint

load_dotenv(dotenv_path='twitch_clients.env')
debug = False
client_id = os.getenv('client_id')# twitch bot
client_secret = os.getenv('client_secret') # twitch bot
dcbot_token = os.getenv('dcbot_token')

with open('users.json','r') as q:
    users = json.load(q)

# -- discord bot logic --
bot = commands.Bot(command_prefix='@',intents=discord.Intents.all())

@bot.event
async def on_ready():
    fprint('ready')

# -- DEFINITIONS --

def get_token():
    # Changes the discord app credentials into an expiring OAuth token, which is needed.
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    return response.json()['access_token']

def error_handling(response, ctx=None):
    global token
    # Error handling for pretty much every API situation. return True means that the program which is running it breaks
    match response.status_code:
        case 400 | 404: #Not Found/Bad Request
            if ctx:
                fprint(f'User not found or invalid request.')
            fprint('error 400 or 404: ', response.text)
            eepy(3)
            return True

        case 401: # Forbidden, invalid token generically
            token = get_token()
            eepy(3)
        
        case 500 | 502 | 503 | 504: # Twitch API 
            if ctx:
                fprint('Twitch API is currently unavailable. Please try again later.')
            eepy(3)
            return True

        case 429: # Rate Limited
            if ctx:
                fprint('Rate limited, please wait.')
            eepy(10)

        case _: # Other errors. If i mess up, may pass 200 201 here.
            if ctx:
                fprint('An unexpected error occurred. Please try again later.')
                fprint(f'error {response.status_code} in adduser: {response.text}')
            eepy(3)
def send_discord_embed(userid, islive): # Technically not an embed, name is for legacy purpose. Just a webhook message.
    # Userid - the ID of the user which is live/offline.
    # islive - If the live or not live message should be sent.

    livename = users[userid]['username']

    match islive:
        case True:
            content = f"<@267440142124449794> {livename} is [live!](https://twitch.tv/{livename})"
        case False:
            content = f"{livename} is now offline..."

    # Send message through webhook
    webhook = DiscordWebhook(
        url=os.getenv('webhook_url'),
        content=content
    )
    webhook.execute()

def get_live_status():
    # Does the API call to check all users if they are live. API request used only returns the users which are currently live, with no info about the ones who aren't.
    global users, headers
    while True:
        try:
            url = f'https://api.twitch.tv/helix/streams?{f"""user_id={"&user_id=".join(users.keys())}"""}'
            response = requests.get(url, headers=headers)

            if response.status_code in [200, 201]:
                for x in users:
                # Checks Live
                    peepo = False

                    # Checks if user x is one of the responses from the API call, and is therefore live.
                    for y in response.json()['data']:
                        if x == y['user_id']:
                            peepo = True
                            break

                    match peepo:
                        case True:
                            fprint(f"{users[x]['username']} [spring_green4]liv[/spring_green4]")

                            if not users[x]['live_status']: # If the user was previously offline, send a notification and update file.
                                send_discord_embed(x, True)
                                users[x]['live_status'] = True
                                with open('users.json','w') as q:
                                    json.dump(users, q, indent=4)

                        case _:
                            fprint(f"{users[x]['username']} [red]not[/red] liv")

                            if users[x]['live_status']: # If the user was previously live, send a notification and update file.
                                send_discord_embed(x, False)
                                users[x]['live_status'] = False
                                with open('users.json','w') as q:
                                    json.dump(users, q, indent=4)

                fprint(randint(1,10000000000)) # So that you can tell when the timer resets and the new API stuff comes in. Also fun.

            else:
                x = error_handling(response)

        except Exception as e:
            fprint(e)

        eepy(3)

def get_title():
    global users, headers
    while True:
        try:
            url = f'https://api.twitch.tv/helix/channels?broadcaster_id={"&broadcaster_id=".join(users.keys())}'
            response = requests.get(url, headers=headers)

            if response.status_code in [200, 201]:
                for entry in response.json()['data']:

                    userindex = users[entry['broadcaster_id']] # The user entry in the json
                    title = entry['title'] # API Title

                    if title != userindex['title']:
                        
                        if userindex['title'] != "": # Checks that title is not set to creation default. Necessary before that which always runs as it looks at userindex, which is changed. Can't be merged with previous if as then userindex will never change from first title.
                            
                            
                            fprint(f'title changed: {title}')
                            
                            embed = {
                                "author": {
                                    "name": f"{userindex['username']}",
                                    "icon_url": f"{userindex['userinfo']['profile_image_url']}",
                                    "url": f"https://twitch.tv/{userindex['username']}"
                                },
                                "title": "Title Change",
                                "fields": [
                                    {
                                    "name": f"{title}",
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
                        
                        # Runs as long as new title != old title, but runs if title is creation default.
                        userindex['title'] = title
                        with open('users.json', 'w') as q:
                            json.dump(users, q, indent=4)

            # Error Handling
            else:
                x = error_handling


        except Exception as e:
            fprint(e)

        eepy(3)

def get_user_info():
    global users, headers
    
    while True:
        try:
            url = f'https://api.twitch.tv/helix/users?login={"&broadcaster_id=".join(users.keys())}'
            response = requests.get(url, headers=headers)


            if response.status_code in [200,201]:
                fprint('got user info')

                for x in response.json()['data']:
                    user_id = x['id']
                    users[user_id]['username'] = x['display_name'] # the display name, a.k.a. the username of the person with captitalization. Used for messages, lists, etc. Used often enough to warrant a variable outside of userinfo.
                    users[user_id]['userinfo'] = x # All of the info about the user. Relevant stuff is pfps and some other smaller stuff for future use.

                with open('users.json','w') as q:
                    json.dump(users, q, indent=4)

            # Error Handling.
            else:
                x = error_handling

        except Exception as e:
            fprint(e)
        
        eepy(600)

# -- DISCORD BOT COMMANDS --

@bot.command()
async def adduser(ctx, twitch_username):
    global users, headers

    while True:
        try:
            url = f'https://api.twitch.tv/helix/users?login={twitch_username}'
            response = requests.get(url, headers=headers)

            if response.status_code in [200, 201] and len(response.json()['data']) > 0: # len command because if the user is nonexistant, it returns 200 but with no data.
                userdata = response.json()['data'][0]

                if userdata['id'] in users: # If the user is already being monitored, don't add them again
                    await ctx.send(f'{twitch_username} is already being monitored.')
                    return

                # Creating the json struct for the new user, and writing to file.
                users[userdata['id']] = { 
                    "username": userdata['display_name'],
                    "userinfo": userdata,
                    "live_status": False,
                    "title": "",
                }

                with open('users.json','w') as q:
                    json.dump(users, q, indent=4)

                await ctx.send(f'Started monitoring {twitch_username}.')
                return
            
            # Error handling
            elif len(response.json()['data']) == 0:
                await ctx.send(f'User {twitch_username} not found.')
                return
            
            else:
                x = error_handling(response, ctx)
                if x == True:
                    return
                
        except RequestException as e:
            fprint(e)

@bot.command()
async def removeuser(ctx, twitch_username):
    global users

    present = False # Is the twitch username one of the users. If it is, that user becomes the present var. | .lower() on both just to make capitalization irrelevant, as twitch usernames are.
    for x in users:
        if users[x]["username"].lower() == twitch_username.lower():
            present = users[x]
            break
    
    if not present: # If they wrote a faulty username
        await ctx.send('Username you sent is not present.')
        return

    # If the username is in fact in users, pops the entry and writes the file.
    users.pop(present['userinfo']['id'])
    with open('users.json', 'w') as q:
        json.dump(users, q, indent=4)
    
    await ctx.send(f'{present["username"]} has been removed.')
   
@bot.command()
async def listusers(ctx):

    prettyusers = '' # the string which becomes the embed text
    for x in users:
        prettyusers += f'**{users[x]["username"]}:** {"Live :red_circle:" if users[x]["live_status"] else "Offline :black_circle:"}\n'
        
    # Creates the embed
    embed = discord.Embed(title="Users being Checked:")
    embed.description = prettyusers if prettyusers else "No users being checked."
    embed.color = discord.Color.from_str("#884dc6")
    embed.set_author(name="Twitch Check Bot")

    await ctx.send(embed=embed)

# -- INIT --

if __name__ == "__main__":
    # Gets the token and defines the overall API header.
    token = get_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Client-Id': client_id,
    }

    # Define and start the 3 threads
    Thread(target=get_live_status).start()
    Thread(target=get_title).start()
    Thread(target=get_user_info).start()

    if not debug:
        bot.run(token=dcbot_token)