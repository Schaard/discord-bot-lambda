import requests
import yaml
import os
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()

# Fetch token from environment variable
TOKEN = os.environ.get('TOKEN')
APPLICATION_ID = os.environ.get('APPLICATION_ID')

WITWID_SERVER = 487095283222839296
URL_GLOBAL = f"https://discord.com/api/v9/applications/{APPLICATION_ID}/commands" #URL for global commands
URL_GUILD = f"https://discord.com/api/v9/applications/{APPLICATION_ID}/guilds/{WITWID_SERVER}/commands" #url for WITWID guild commands

guild_command_mode = False
if not guild_command_mode:
    URL = URL_GLOBAL
else:
    URL = URL_GUILD

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Use os.path.join to create the full path to the YAML file
yaml_path = os.path.join(script_dir, "discord_commands.yaml")

with open(yaml_path, "r") as file:
    yaml_content = file.read()

commands = yaml.safe_load(yaml_content)
headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

delete_global_commands = False
if delete_global_commands:
    # DELETE ALL GLOBAL-LEVEL COMMANDS
    # First, get all existing GLOBAL commands
    response = requests.get(URL_GLOBAL, headers=headers)
    existing_commands = response.json()
    if response.status_code == 200:
        # If there are existing commands, delete them
        if existing_commands:
            for command in existing_commands:
                delete_url = f"{URL_GLOBAL}/{command['id']}"
                delete_response = requests.delete(delete_url, headers=headers)
                if delete_response.status_code == 204:
                    print(f"Successfully deleted command: {command['name']}")
                else:
                    print(f"Failed to delete command: {command['name']}. Status code: {delete_response.status_code}")
        else:
            print("No global commands found.")
        
        print("All global commands have been cleared.")
    else:
        print(f"Failed to retrieve global commands. Status code: {response.status_code}")
        print(f"Response: {response.text}")

delete_guild_commands = False
if delete_guild_commands:
    # DELETE ALL GUILD-LEVEL COMMANDS
    # First, get all existing GUILD commands
    response = requests.get(URL_GUILD, headers=headers)
    existing_commands = response.json()
    if response.status_code == 200:
        # If there are existing commands, delete them
        if existing_commands:
            for command in existing_commands:
                delete_url = f"{URL_GUILD}/{command['id']}"
                delete_response = requests.delete(delete_url, headers=headers)
                if delete_response.status_code == 204:
                    print(f"Successfully deleted command: {command['name']}")
                else:
                    print(f"Failed to delete command: {command['name']}. Status code: {delete_response.status_code}")
        else:
            print("No GUILD commands found.")
        
        print("All GUILD commands have been cleared.")
    else:
        print(f"Failed to retrieve GUILD commands. Status code: {response.status_code}")
        print(f"Response: {response.text}")


# Bulk update approach
def handle_rate_limit(response):
    if response.status_code == 429:
        print(f"Rate limited. Waiting for {5} seconds.")
        time.sleep(5)
        return True
    return False

submit_commands = True
if submit_commands:
    response = requests.put(URL, json=commands, headers=headers)
    if handle_rate_limit(response):
        response = requests.put(URL, json=commands, headers=headers)

print(f"Response status: {response.status_code}")
print(f"Response body: {response.text}")