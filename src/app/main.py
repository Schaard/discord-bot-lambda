import os
import logging
from flask import Flask, jsonify, request, Response
from mangum import Mangum
from asgiref.wsgi import WsgiToAsgi
from discord_interactions import verify_key_decorator
from database import DynamoDBHandler
from dotenv import load_dotenv
import json
import boto3
from datetime import datetime, timedelta, timezone
import requests
import random
import re
import string
import discord

#set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#build the flask app w async wrapper and mangum
app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
handler = Mangum(asgi_app, lifespan="off")

# Load environment variables from .env file
load_dotenv()

# Initialize the DynamoDB handler
db = DynamoDBHandler(os.environ.get("DYNAMODB_TABLE_NAME"))
DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")

def mention_user(user_id):
    return f"<@{user_id}>"
def get_name_fromid(user_id):
    url = f"https://discord.com/api/v10/users/{user_id}"
    headers = {
        "Authorization": f"Bot {os.environ.get('TOKEN')}"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        user_data = response.json()
        return user_data['username']  # Returns the username
    else:
        print(f"Failed to fetch user: {response.status_code} - {response.text}")
        return None
def sanitize_input(user_input: str) -> str:
    if not isinstance(user_input, str):
        raise ValueError("Input must be a string")

    # Strip leading and trailing whitespace
    sanitized_input = user_input.strip()

    # Strip leading and trailing whitespace
    sanitized_input = user_input.strip('"\'')

    # Remove control characters like newlines, tabs, etc.
    sanitized_input = re.sub(r'[\n\r\t]', ' ', sanitized_input)

    # Optionally remove any non-printable characters (Unicode and ASCII control characters)
    sanitized_input = re.sub(r'[^\x20-\x7E]', '', sanitized_input)

    # Escape or remove potentially harmful characters (e.g., for HTML contexts)
    sanitized_input = sanitized_input.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')

    # Limit length if necessary (DynamoDB supports up to 400 KB for string values)
    if len(sanitized_input) > 1000:  # Set your own length limit
        sanitized_input = sanitized_input[:1000]

    return sanitized_input
def get_user_name(raw_request, user_id):
    #print the user name 
    try:
        user_info = raw_request['data']['resolved']['users'][f"{user_id}"]["username"]
    except Exception as e:
        #logger.error(f"Name not found in raw_request: {e}")
        user_info = get_name_fromid(user_id)
    
    return user_info

def has_active_entitlement(guild_id, sku_id, entitlements):
    # Check if any entitlement matches the guild and SKU ID
    for entitlement in entitlements:
        if entitlement.get('guild_id') == guild_id and entitlement.get('sku_id') == sku_id:
            # Check if entitlement is active
            if entitlement.get('ends_at') is None:  # Active entitlement
                return True
    return False
def send_report(guild_id, active_entitlement):
    # Generate a monthly report for the server (guild)
    
    # Generate the report using your DynamoDB handler
    report, channel_to_post_in = generate_report(guild_id, active_entitlement)

    report = {
        "content": "",
        "tts": False,
        "embeds": report['data']['embeds'],
        "components": report['data']['components']
    }

    # Send the message to Discord
    url = f"https://discord.com/api/v10/channels/{channel_to_post_in}/messages"
    headers = {
        "Authorization": f"Bot {os.environ.get('TOKEN')}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, json=report, headers=headers)
    
    if response.status_code == 200:
        logger.info(f"Report sent successfully to guild {guild_id}")
    else:
        logger.error(f"Failed to send report to guild {guild_id}. Status code: {response.status_code}, Response: {response.text}")

    return response.status_code == 200
def generate_report(server_id, active_entitlement = False):
    # Generate a monthly report for the server (guild)
    # Set the time range for the current month
    #today = datetime.utcnow()

    def get_last_day_of_month(any_day):
        # The day 28 exists in every month. 4 days later, it's always next month
        next_month = any_day.replace(day=28) + timedelta(days=4)
        # subtracting the number of the current day brings us back to the end of current month
        return next_month - timedelta(days=next_month.day)
    # Get current time in UTC
    today = datetime.now(timezone.utc)

    # Calculate first day of the month
    first_day_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Calculate last day of the month
    last_day_of_month = get_last_day_of_month(today)

    # Generate the report using your DynamoDB handler
    print(f"Getting Report for Server ID: {server_id}")
    monthly_report, channel_to_post_in = db.get_wrapped_report(server_id, first_day_of_month, last_day_of_month, active_entitlement)
    print(f"Monthly report: {monthly_report} + Channel: {channel_to_post_in}")
    embed_dict = monthly_report.to_dict()
    # Return the report as a message to the channel

    components = []    
    if not active_entitlement:
        print("Trying to attach premium button")
        components = [               
            {
                "type": 1,  # ACTION_ROW
                "components": [
                    {
                        "type": 2,  # BUTTON
                        "style": 6,  # PRIMARY
                        "sku_id": "1296369498529730622"
                    }
                ]
            }
        ]

    
    response_data = {
        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
        "data": {
            "embeds": [embed_dict],
            "components": components
        }
    }
    return response_data, channel_to_post_in
                    
def send_reports_to_all_guilds():

    guild_list = get_all_guilds(os.environ.get("TOKEN"))
    for guild in guild_list:
        guild_id = guild['id']
        guild_is_premium = guild['has_entitlement']
        print(f"Sending report to guild {guild_id}")
        success = send_report(guild_id, guild_is_premium)
        if not success:
            logger.warning(f"Failed to send report to guild {guild_id}")

def get_all_guilds(bot_token):
    application_id = os.environ.get('APPLICATION_ID')
    sku_id = '1296369498529730622'    
    
    # First, get all entitled guilds
    entitled_guilds = set()
    entitlements_url = f"https://discord.com/api/v10/applications/{application_id}/entitlements"
    entitlements_headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }
    entitlements_params = {
        "sku_ids": sku_id,
        "limit": 100,
        "exclude_ended": True
    }

    while True:
        entitlements_response = requests.get(entitlements_url, headers=entitlements_headers, params=entitlements_params)
        if entitlements_response.status_code != 200:
            print(f"Error fetching entitlements: {entitlements_response.status_code}, {entitlements_response.text}")
            break
        
        entitlements = entitlements_response.json()
        for entitlement in entitlements:
            if entitlement.get('guild_id'):
                entitled_guilds.add(entitlement['guild_id'])
        
        if len(entitlements) < 100:
            break

        # Prepare for the next page
        entitlements_params["after"] = entitlements[-1]["id"]

    print(f"Entitled Guilds: {entitled_guilds}")

    # Now, get all guilds and mark which ones are entitled
    url = "https://discord.com/api/v10/users/@me/guilds"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }
    #print(headers)
    params = {
        "limit": 200,
        "with_counts": True  # Include member counts if needed
    }
    
    all_guilds = []
    
    while True:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Error: {response.status_code}, {response.text}")
            break
        
        guilds = response.json()
        for guild in guilds:
            guild['has_entitlement'] = guild['id'] in entitled_guilds
            all_guilds.append(guild)
        
        if len(guilds) < 200:
            break  # We've reached the end of the list
        
        # Prepare for the next page
        params["after"] = guilds[-1]["id"]
    
    return all_guilds

#MAIN ROUTE *******************
@app.route("/", methods=["POST"])
async def interactions():
    print(f"👉 Request: {request.json}")
    raw_request = request.json

    
    sku_id = '1296369498529730622'  
    entitlements = raw_request.get('entitlements', [])
    #handle ping interactions so they dont crash other stuff

    active_entitlement = False
    if raw_request["type"] != 1:
        guild_id = raw_request.get('guild_id', None)
        if guild_id is None:
            guild_id = raw_request.get('guild', {}).get['id']

        if guild_id is None:
            return jsonify({"error": "Invalid request: guild_id not provided"}), 400
        # Check for active entitlement
        active_entitlement = has_active_entitlement(guild_id, sku_id, entitlements)
    
    if active_entitlement:
        logging.info("Active entitlement found. PREMIUM MODE ENABLED")
    else:
        logging.info("No active entitlement found.")
    

    #handle eventbridge payloads
    # Check if this is an EventBridge trigger
    if raw_request.get('interaction_token', "") == "MonthlyReportTriggered" and raw_request.get('application_id', "") == "1279716753127243786":
        logging.info("!!!!!!EventBridge trigger received!!!!!!!!!")
        send_reports_to_all_guilds()
        pass


    final_response = interact(raw_request, active_entitlement)

    return final_response

#INTERACT FUNCTION
@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interact(raw_request, active_entitlement):
    if raw_request["type"] == 1:  # PING
        return jsonify({"type": 1}) # PONG
           
    match raw_request["type"]:
        case 2:  # APPLICATION_COMMAND
            data = raw_request["data"]
            command_name = data["name"]
            logger.info("Application command received")
            user_id = raw_request["member"]["user"]["id"]
            server_id = raw_request["guild_id"]
            match command_name:                 
                case "help":
                        try:
                            # Create an embed for the help command
                            embed = discord.Embed(
                                title="GrudgeKeeper Help",
                                description="Here are the available commands for GrudgeKeeper:",
                                color=discord.Color.blue().value,
                                timestamp=datetime.now()
                            )
                            embed.add_field(
                                name="/grudge <killer>",
                                value="Victim of friendly fire? Record a grudge against your trigger-happy teammate.",
                                inline=False
                            )
                            embed.add_field(
                                name="/oops <victim>",
                                value="Killed your friend? Record a grudge on their behalf.",
                                inline=False
                            )
                            embed.add_field(
                                name="/grudgelist <user1> [user2]",
                                value="List incidents between two users. If user2 is blank, shows those between user1 and you.",
                                inline=False
                            )
                            # Add fields for each command
                            embed.add_field(
                                name="/hallofshame",
                                value="Show the worst teamkillers on the server.",
                                inline=False
                            )
                            embed.add_field(
                                name="/help",
                                value="Show this help message.",
                                inline=False
                            )

                            # Set thumbnail and footer
                            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/553164743720960010/1296332288484708383/icon64.png?ex=6711e706&is=67109586&hm=90dd6486c2ba6e755b6cdca80182867367bfe95cbb627bba7b03472d3ce3a01d&")
                            footer_text = "Grudgekeeper Free resets monthly. Premium ($1.99) grudges are eternal." if not active_entitlement else "Generated by GrudgeKeeper Premium"
                            embed.set_footer(
                                text=footer_text,
                                icon_url="https://cdn.discordapp.com/attachments/553164743720960010/1296352648001359882/icon32.png?ex=6711f9fc&is=6710a87c&hm=1d1dfe458616c494f06d4018f7bad0e7dd6a9590f742d003742821183125509e&"
                            )

                            # Convert the embed to a dict
                            embed_dict = embed.to_dict()

                            # Prepare the response
                            response_data = {
                                "type": 4,
                                "data": {
                                    "embeds": [embed_dict]
                                }
                            }
                            # Add premium button if entitlement is not active
                            if not active_entitlement:
                                response_data["data"]["components"] = [
                                    {
                                        "type": 1,  # Action Row
                                        "components": [
                                            {
                                                "type": 2,  # Button
                                                "style": 5,  # Link button
                                                "label": "Upgrade to Premium ($1.99)",
                                                "url": "https://discord.com/application-directory/1296369498529730622"
                                            }
                                        ]
                                    }
                                ]
                            return jsonify(response_data)
                        except Exception as e:
                            logger.error(f"Error generating help message: {str(e)}")
                            response_data = {
                                "type": 4,
                                "data": {"content": f"Error generating help message: {str(e)}"}
                            }
                        
                        return jsonify(response_data)
                                
                #case "report":
                #    
                #    this_guild_id = str(raw_request["guild_id"])
                #    response_data, channel_to_post_in = generate_report(this_guild_id)
                #    return jsonify(response_data)       
                     
                case "grudge":
                    killer = data["options"][0]["value"]
                    
                    # Trigger a modal to collect inputs instead of processing command arguments directly
                    response_data = {
                        "type": 9,  # MODAL
                        "data": {
                            "custom_id": f"grudge_modal_{user_id}_{killer}",
                            "title": "Record a Grudge",
                            "components": [
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "cause_of_death_input",
                                            "style": 2,  # Short input
                                            "label": "Cause of Death (optional)",
                                            "placeholder": "What was the cause of death?",
                                            "required": False,
                                            "max_length": 250
                                        }
                                    ]
                                },
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "last_words_input",
                                            "style": 2,  # Paragraph input (multi-line)
                                            "label": "Last Words (optional)",
                                            "placeholder": "What was said?",
                                            "required": False,
                                            "max_length": 250
                                        }
                                    ]
                                },
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "Evidence",
                                            "style": 1,  
                                            "label": "Link to Evidence (optional)",
                                            "placeholder": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                            "required": False,
                                            "max_length": 250
                                        }
                                    ]
                                },
                            ]
                        }
                    }
                    return jsonify(response_data)
                case "oops":
                    victim = data["options"][0]["value"]
                    vname = get_name_fromid(victim)
                    # Trigger a modal to collect inputs instead of processing command arguments directly
                    response_data = {
                        "type": 9,  # MODAL
                        "data": {
                            "custom_id": f"oops_modal_{user_id}_{victim}",
                            "title": f"Record a Grudge on Behalf of {vname}",
                            "components": [
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "cause_of_death_input",
                                            "style": 2,  # Short input
                                            "label": "Cause of Death (optional)",
                                            "placeholder": "What was the cause of death?",
                                            "required": False,
                                            "max_length": 250
                                        }
                                    ]
                                },
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "last_words_input",
                                            "style": 2,  # Paragraph input (multi-line)
                                            "label": "Last Words (optional)",
                                            "placeholder": "What was said over voice chat?",
                                            "required": False,
                                            "max_length": 250
                                        }
                                    ]
                                },
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "Evidence",
                                            "style": 1,  # Paragraph input (multi-line)
                                            "label": "Link to Evidence (optional)",
                                            "placeholder": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                            "required": False,
                                            "max_length": 250
                                        }
                                    ]
                                },
                            ]
                        }
                    }
                    return jsonify(response_data)
                case "grudgelist":
                    try:
                        options = data.get("options", [])
                        page = 0  # Default to first page
                        logging.info(f"Number of options: {len(options)}")
                        grudge_depth = 8
                        page = 0
                        
                        
                        if len(options) == 1:
                            # Report between calling user and specified user
                            target_user = options[0]["value"]
                            user1 = user_id
                            user2 = target_user
                            report, has_more = db.generate_grudge_report(user_id, target_user, grudge_depth, page, raw_request["guild_id"], active_entitlement)
                        elif len(options) == 2:
                            # Report between two specified users
                            user1 = options[0]["value"]
                            user2 = options[1]["value"]
                            report, has_more = db.generate_grudge_report(user1, user2, grudge_depth, page, raw_request["guild_id"], active_entitlement)
                        else:
                            raise ValueError("Invalid number of arguments for grudgereport")
                        #logging.info(f"Grudge report generated: {report}")
                        logging.info(f"Result from generate_grudge_report: {report}")
                        
                        #Determine the next page number based on premium status
                        next_page = page + 1 if active_entitlement else page
                        
                        #Make the button if there's more!
                        components = []
                        if has_more:
                            logging.info("Has more")
                            components = [
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 2,  # BUTTON
                                            "style": 1,  # PRIMARY
                                            "label": "Older",
                                            "custom_id": f"grudgereport_pagination_{user1}_{user2}_{next_page}"
                                        }
                                    ]
                                }
                            ]
                        
                        response_data = {
                            "type": 4,
                            "data": {
                                "embeds": [report],
                                "components": components if has_more else []
                                }
                        }
                    except Exception as e:
                        logger.error(f"Error generating grudge report: {str(e)}")
                        response_data = {
                            "type": 4,
                            "data": {"content": f"Error generating grudge report: {str(e)}"}
                        }
                    logging.info(f"Grudges response data: {response_data}")
                    return jsonify(response_data)
                case "hallofshame":
                    try:
                        this_server_id = raw_request["guild_id"]
                        
                        top_killers = db.get_top_killers(this_server_id, active_entitlement)  # Get top 5 killers
                        
                        # Create an embed
                        embed = discord.Embed(title="🏆 Hall of Shame 🏆", 
                                            description="Players with the most unforgiven kills.",
                                            timestamp=datetime.now(),
                                            color=discord.Color.blue().value)  # You can choose any color you like
                        
                        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/553164743720960010/1296332288484708383/icon64.png?ex=6711e706&is=67109586&hm=90dd6486c2ba6e755b6cdca80182867367bfe95cbb627bba7b03472d3ce3a01d&")
                                        # Highlighted message about reset vs. premium grudge retention

                        
                        footer_text = "Generated by GrudgeKeeper Free" if not active_entitlement else "Generated by GrudgeKeeper Premium"
                        embed.set_footer(
                        text=f"{footer_text}",
                        icon_url="https://cdn.discordapp.com/attachments/553164743720960010/1296352648001359882/icon32.png?ex=6711f9fc&is=6710a87c&hm=1d1dfe458616c494f06d4018f7bad0e7dd6a9590f742d003742821183125509e&"
                        )     

                        if top_killers:
                            for i, (killer_id, kill_count) in enumerate(top_killers, 1):
                                name = get_name_fromid(killer_id)
                                embed.add_field(name=f"{i}. {name}: ({kill_count} kills)", value="", inline=False)                            
                        else:
                            embed.description += "\nThe Hall of Shame is empty. Be the first to make a mistake!"
                        
                        if active_entitlement:
                            highlight_title = "\n👁️ The Hall is Eternal 👁️"
                            highlight_message = "GrudgeKeeper Premium's Hall of Shame reflects grudges across all time."
                        else:
                            highlight_title = "\n🌘 Monthly Hall of Shame 🌘"
                            highlight_message = "GrudgeKeeper Free's Hall of Shame resets monthly. GrudgeKeeper Premium preserves shame forever."

                        # Add the message as a new field for high visibility
                        embed.add_field(
                            name=highlight_title,
                            value=highlight_message,
                            inline=False  # Making it full-width for emphasis
                        )
                    except Exception as e:
                            # In case of an error, create an error embed
                            embed = discord.Embed(title="Error", 
                                                description=f"Error retrieving Hall of Shame: {str(e)}",
                                                color=discord.Color.blue().value)
                    # Convert the embed to a dict for the response
                    embed_dict = embed.to_dict()

                    components = []    
                    if not active_entitlement:
                        print("Trying to attach premium button")
                        components = [               
                            {
                                "type": 1,  # ACTION_ROW
                                "components": [
                                    {
                                        "type": 2,  # BUTTON
                                        "style": 6,  # PRIMARY
                                        "sku_id": "1296369498529730622"
                                    }
                                ]
                            }
                        ]

                    response_data = {
                        "type": 4,
                        "data": {
                            "embeds": [embed_dict],
                            "components": components
                        }
                    }
                    return jsonify(response_data)                 
                case _:
                    message_content = "Command recognized but not implemented yet."
            response_data = { 
                "type": 4,
                "data": {"content": message_content},
            }
            return jsonify(response_data)
        case 3:  # MESSAGE_COMPONENT
            logger.info("Message component received")

            #return strings as ethereal messages 
            result = handle_component_interaction(raw_request, active_entitlement)
            logger.info(f"Message Result: {result}")
            if isinstance(result, str):
                logger.info("Responding with ephemeral message")
                return jsonify({
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": result,
                    "flags": 64  # EPHEMERAL
                }
            })
            elif isinstance(result, dict):
                logger.info("Responding with pre-formed JSON response")
                return jsonify(result)
            
            #If not string, Respond immediately with 202 Accepted
            logger.info(f"Responding with 202!!!!!!!!!!")
            response = Response('', 202)
            return response            
        case 4:  # APPLICATION_COMMAND_AUTOCOMPLETE
            logger.info("Autocomplete received")
        case 5:  # MODAL_SUBMIT 
            data = raw_request["data"]
            custom_id = data["custom_id"]
            parts = custom_id.split("_")
            # The custom_id is structured like: "oops_modal_{user_id}_{victim}"
            modal_type = parts[0]
            match modal_type:
                case "oops":
                    logger.info("Oops modal submit received")                    
                    data = raw_request["data"]
                    custom_id = data["custom_id"]
                    user_id = parts[2]  # Extract the user ID from the custom_id
                    victim = parts[3] # Extract the victim ID from the custom_id

                    # Process other modal inputs
                    cause_of_death = data["components"][0]["components"][0]["value"]
                    cause_of_death = sanitize_input(cause_of_death)
                    last_words = data["components"][1]["components"][0]["value"]
                    last_words = sanitize_input(last_words)
                    evidence_link = data["components"][2]["components"][0]["value"]
                    if len(evidence_link) > 2024: evidence_link = evidence_link[:2024]
                    #unforgivable = interpret_boolean_input(unforgivable)
                    
                    #can't forgive your own oops 
                    forgiven = False
                    
                    # Retrieve the server, game, and channel IDs
                    server_id = str(raw_request["guild_id"])
                    game_id = "default_game_id"  # Replace with the actual game ID
                    channel_id = str(raw_request["channel_id"])

                    # Get the current UTC time and format it as ISO 8601 string
                    timestamp = datetime.now(timezone.utc).isoformat()

                    # Now you can use the victim ID along with other modal input data
                    try:
                        db.add_kill(user_id, user_id, victim, cause_of_death, server_id, game_id, channel_id, timestamp, False, forgiven, evidence_link)

                        grudge_announcement_message = get_grudge_announcement()

                        # Construct the message_content dynamically
                        if cause_of_death is None or cause_of_death == "":
                            content_for_kill_message = f"{mention_user(user_id)} killed {mention_user(victim)}!"
                        else:
                            content_for_kill_message = f"{mention_user(user_id)} killed {mention_user(victim)} by {cause_of_death}!"

                        if last_words:
                            content_for_kill_message += f' Their last words were: "{last_words}"'

                        if evidence_link:
                            content_for_kill_message += f' The evidence: {evidence_link}'
                        #if unforgivable:
                        #    content_for_kill_message += " This grudge has been marked UNFORGIVABLE!"

                        #if not unforgivable and forgiven:
                        #    content_for_kill_message += f" {get_name_fromid(victim)} forgave them instantly."

                        user_kills = db.get_unforgivencount_on_user(user_id, victim, server_id, active_entitlement)
                        compare_kills = db.get_unforgivencount_on_user(victim, user_id, server_id, active_entitlement)
                        user_name = get_user_name(raw_request, victim)
                        victim_name = get_user_name(raw_request, user_id)
                        end_of_kill_message = f"{get_grudge_description(raw_request, user_id, user_kills, victim, compare_kills)}"                                                
                        
                        
                        
                        content_for_grudge_message = ""
                        if user_kills > compare_kills:
                            content_for_grudge_message += f"\nWith {user_kills} unforgiven deaths from {victim_name} and {compare_kills} in return, {end_of_kill_message} ({user_kills - compare_kills})"
                        else:
                            content_for_grudge_message += f"\nWith {compare_kills} unforgiven deaths from {user_name} and {user_kills} in return, {end_of_kill_message} ({compare_kills - user_kills})"
                        content_for_grudge_message += f"\n\n{user_name.capitalize()}: will you forgive or keep the grudge?"
                        
                        # Create an embed
                        embed = discord.Embed(
                            title=f"{grudge_announcement_message}",
                            description=content_for_kill_message,
                            color=discord.Color.blue().value ,
                            timestamp=datetime.now()
                        )
                        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/553164743720960010/1296332288484708383/icon64.png?ex=6711e706&is=67109586&hm=90dd6486c2ba6e755b6cdca80182867367bfe95cbb627bba7b03472d3ce3a01d&")
                        footer_text = "Generated by GrudgeKeeper Free" if not active_entitlement else "Generated by GrudgeKeeper Premium"
                        embed.set_footer(
                        text=f"{footer_text}",
                        icon_url="https://cdn.discordapp.com/attachments/553164743720960010/1296352648001359882/icon32.png?ex=6711f9fc&is=6710a87c&hm=1d1dfe458616c494f06d4018f7bad0e7dd6a9590f742d003742821183125509e&"
                        )
                        embed.add_field(name="\u200b", value=content_for_grudge_message, inline=False)
                        # Convert the embed to a dict
                        embed_dict = embed.to_dict()

                        logging.info(f"Sending forgiveness embed: {embed_dict}")
                        # Create a response with a button
                        response_data = {
                            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                            "data": {
                                "embeds": [embed_dict],
                                "components": [
                                    {
                                        "type": 1,  # ACTION_ROW
                                        "components": [
                                            {
                                                "type": 2,  # Button
                                                "label": "Forgive (-1 Grudge)",  # Supportive and positive action
                                                "style": 1,  # Green button (Success)
                                                "custom_id": f"forgive_{user_id}_{victim}_{timestamp}"
                                            },
                                            {
                                                "type": 2,  # Button
                                                "label": "Keep Grudge",  # Not forgiving action
                                                "style": 4,  # Red button (Danger)
                                                "custom_id": f"grudge_{user_id}_{victim}_{timestamp}"
                                            }
                                        ]
                                    }
                                ]
                            }
                        }

                        if forgiven:
                            response_data["data"]["components"] = []

                        logger.info(f"returning modal input response data {response_data}")
                        return jsonify(response_data)
                    except Exception as e:
                        return jsonify({"type": 4, "data": {"content": f"Error recording oops: {str(e)}"}})
                case "grudge":
                    logger.info("Grudge modal submit received")                    
                    data = raw_request["data"]
                    custom_id = data["custom_id"]
                    victim_id = parts[2] # Extract the victim ID from the custom_id
                    killer_id = parts[3]  # Extract the user ID from the custom_id
                    
                    # Process other modal inputs
                    cause_of_death = data["components"][0]["components"][0]["value"]
                    cause_of_death = sanitize_input(cause_of_death)
                    last_words = data["components"][1]["components"][0]["value"]
                    last_words = sanitize_input(last_words)
                    evidence_link = data["components"][2]["components"][0]["value"]
                    if len(evidence_link) > 500: evidence_link = evidence_link[:500]
                    #unforgivable = interpret_boolean_input(unforgivable)
                    forgiven = False
                    #forgiven = interpret_boolean_input(forgiven)
                    
                    # Retrieve the server, game, and channel IDs
                    server_id = str(raw_request["guild_id"])
                    game_id = "default_game_id"  # Replace with the actual game ID
                    channel_id = str(raw_request["channel_id"])

                    # Get the current UTC time and format it as ISO 8601 string
                    timestamp = datetime.now(timezone.utc).isoformat()

                    # Now you can use the victim ID along with other modal input data
                    try:
                        db.add_kill(victim_id, killer_id, victim_id, cause_of_death, server_id, game_id, channel_id, timestamp, False, forgiven, evidence_link)
                        grudge_announcement_message = get_grudge_announcement()
                        # Construct the message_content dynamically
                        if cause_of_death is None or cause_of_death == "":
                            content_for_kill_message = f"{mention_user(killer_id)} killed {mention_user(victim_id)}!"
                        else:
                            content_for_kill_message = f"{mention_user(killer_id)} killed {mention_user(victim_id)} by {cause_of_death}!"

                        if last_words:
                            content_for_kill_message += f' Their last words were: "{last_words}"'
                        
                        if evidence_link:
                            content_for_kill_message += f' The evidence: {evidence_link}'
                        #if unforgivable:
                        #    content_for_kill_message += " This grudge has been marked UNFORGIVABLE!"

                        #if not unforgivable and forgiven:
                        #    content_for_kill_message += f" {get_name_fromid(victim)} forgave them instantly."

                        killer_kills = db.get_unforgivencount_on_user(killer_id, victim_id, server_id, active_entitlement)
                        victim_kills = db.get_unforgivencount_on_user(victim_id, killer_id, server_id, active_entitlement)
                        killer_name = get_user_name(raw_request, killer_id)
                        victim_name = get_user_name(raw_request, victim_id)
                        logging.info(f"victim name: {victim_name} victim_kills: {victim_kills}, killer name: {killer_name} killer_kills: {killer_kills}")
                        end_of_kill_message = f"{get_grudge_description(raw_request, killer_id, killer_kills, victim_id, victim_kills)}"
                        content_for_grudge_message = ""
                        if victim_kills > killer_kills:
                            content_for_grudge_message += f"\nWith {victim_kills} unforgiven deaths from {victim_name} and {killer_kills} in return, {end_of_kill_message} ({victim_kills - killer_kills})"
                        else:
                            content_for_grudge_message += f"\nWith {killer_kills} unforgiven deaths from {killer_name} and {victim_kills} in return, {end_of_kill_message} ({killer_kills - victim_kills})"
                        content_for_grudge_message += f"\n\n{victim_name.capitalize()}: will you forgive or keep the grudge?"                        
                        # Create an embed
                        embed = discord.Embed(
                            title=f"{grudge_announcement_message}",
                            description=content_for_kill_message,
                            color=discord.Color.blue().value ,
                            timestamp=datetime.now()
                        )
                        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/553164743720960010/1296332288484708383/icon64.png?ex=6711e706&is=67109586&hm=90dd6486c2ba6e755b6cdca80182867367bfe95cbb627bba7b03472d3ce3a01d&")
                        footer_text = "Generated by GrudgeKeeper Free" if not active_entitlement else "Generated by GrudgeKeeper Premium"
                        embed.set_footer(
                        text=f"{footer_text}",
                        icon_url="https://cdn.discordapp.com/attachments/553164743720960010/1296352648001359882/icon32.png?ex=6711f9fc&is=6710a87c&hm=1d1dfe458616c494f06d4018f7bad0e7dd6a9590f742d003742821183125509e&"
                        )
                        embed.add_field(name="\u200b", value=content_for_grudge_message, inline=False)
                        # Convert the embed to a dict
                        embed_dict = embed.to_dict()

                        logging.info(f"Sending forgiveness embed: {embed_dict}")

                        # Create a response with a button
                        response_data = {
                            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                            "data": {
                                "embeds": [embed_dict],
                                "components": [
                                    {
                                        "type": 1,  # ACTION_ROW
                                        "components": [
                                            {
                                                "type": 2,  # Button
                                                "label": "Forgive (-1 Grudge)",  # Supportive and positive action
                                                "style": 1,  # Green button (Success)
                                                "custom_id": f"forgive_{killer_id}_{victim_id}_{timestamp}"
                                            },
                                            {
                                                "type": 2,  # Button
                                                "label": "Keep Grudge",  # Not forgiving action
                                                "style": 4,  # Red button (Danger)
                                                "custom_id": f"grudge_{killer_id}_{victim_id}_{timestamp}"
                                            }
                                        ]
                                    }
                                ]
                            }
                        }

                        if forgiven:
                            response_data["data"]["components"] = []

                        logger.info(f"returning modal input response data {response_data}")
                        return jsonify(response_data)                    
                    except Exception as e:
                        return jsonify({"type": 4, "data": {"content": f"Error recording oops: {str(e)}"}})

#forgiveness
def get_random_forgiveness_message(postforgiveness_grudge_description):
    messages = [
        f"After this mercy, it has now changed to: \n**{postforgiveness_grudge_description}**",
        
        f"Following forgiveness, it has shifted to: \n**{postforgiveness_grudge_description}**",
        
        f"Now, after forgiveness, it has reduced to: \n**{postforgiveness_grudge_description}**",
        
        f"In the wake of forgiveness, it is now: \n**{postforgiveness_grudge_description}**",
        
        f"Forgiveness has transformed it into: \n**{postforgiveness_grudge_description}**",
        
        f"Now, post-forgiveness, it is : \n**{postforgiveness_grudge_description}**",
        
        f"After this moment of mercy, it has changed to: \n**{postforgiveness_grudge_description}**",
        
        f"Now, it has lessened to: \n**{postforgiveness_grudge_description}**"
    ]
    
    return random.choice(messages)
def handle_forgive_button(raw_request, active_entitlement):
    # Extract the custom_id from the interaction
    custom_id = raw_request['data']['custom_id']
    server_id = raw_request['guild_id']
    # Parse the custom_id to get the relevant fields
    action, user_id, victim, timestamp = custom_id.split('_')
    
    #Detect if this is someone with the option to forgive themselves
    self_forgive = True if victim == user_id else False

    # Convert the string back to a datetime object
    pretty_timestamp = datetime.fromisoformat(timestamp)
    # Format the timestamp to be more readable
    pretty_timestamp = pretty_timestamp.strftime("%B %d, %Y at %I:%M %p (UTC)")
    victim_name = get_name_fromid(victim)
    user_name = get_name_fromid(user_id)
    
    # Create an embed
    embed = discord.Embed(
        title="Grudge Update",
        color=discord.Color.green().value if action == "forgive" else discord.Color.red().value,
        timestamp=datetime.now()
    )

    if action == "forgive":
        #forgiveness_message = f"{victim_name} has forgiven {mention_user(user_id)}'s friendly fire incident."
        embed.description = f"{victim_name} has forgiven their grudge against {mention_user(user_id)}."
        # Use the parsed information to mark the specific kill as forgiven in the database
        db.forgive_kill(user_id, victim, timestamp)
       
        user_unforgiven_count = db.get_unforgivencount_on_user(user_id, victim, server_id, active_entitlement)
        victim_unforgiven_count = db.get_unforgivencount_on_user(victim, user_id, server_id, active_entitlement)
        
        grudgeholder_id = user_id if user_unforgiven_count < victim_unforgiven_count else victim
        grudgeholder_name = user_name if grudgeholder_id == user_id else victim_name
        new_grudge = db.get_grudge_string(user_id, db.get_unforgivencount_on_user(user_id, victim, server_id, active_entitlement), victim, db.get_unforgivencount_on_user(victim, user_id, server_id, active_entitlement), False)
        grudge_adjustment_string = get_random_forgiveness_message(new_grudge)
        
        embed.add_field(name="\u200b", value=grudge_adjustment_string, inline=False)
        #forgiveness_message += f"\n{grudge_adjustment_string}"
    elif action == "grudge":
        forgivee_name = f"{mention_user(user_id)}" if self_forgive == False else "themselves"
        embed.description = f"{victim_name} will never forgive {forgivee_name} for this."
    
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/553164743720960010/1296332288484708383/icon64.png?ex=6711e706&is=67109586&hm=90dd6486c2ba6e755b6cdca80182867367bfe95cbb627bba7b03472d3ce3a01d&")
    footer_text = "Generated by GrudgeKeeper Free" if not active_entitlement else "Generated by GrudgeKeeper Premium"
    embed.set_footer(
    text=f"{footer_text}",
    icon_url="https://cdn.discordapp.com/attachments/553164743720960010/1296352648001359882/icon32.png?ex=6711f9fc&is=6710a87c&hm=1d1dfe458616c494f06d4018f7bad0e7dd6a9590f742d003742821183125509e&"
    )

    # Convert the embed to a dict
    embed_dict = embed.to_dict()

    logging.info(f"Sending forgiveness embed: {embed_dict}")

    # Start the step function to send the embed
    start_message_step_function(raw_request, None, embed_dict, None, True)

    #logging.info(f"Sending forgiveness_message: {forgiveness_message}")
    #start_message_step_function(raw_request, [forgiveness_message], [], True)    
def remove_article(description):
    articles = ["a ", "an "]  # The articles to check for
    for article in articles:
        if description.startswith(article):
            return description[len(article):]  # Remove the article
    return description
def get_grudge_description(raw_request, user_id, user_kills, compare_user, compare_kills, no_article = False):
    """
    Generate a description of the current grudge state, with handling for counter-norm movements
    when a grudge decreases but remains significant.
    
    :param raw_request: The raw request context.
    :param user_id: The ID of the user (killer).
    :param user_kills: The number of kills the user has.
    :param compare_user: The ID of the compared user (victim).
    :param compare_kills: The number of kills the compared user has.
    :param no_article: Flag to remove articles from the description (optional).
    :param kill_adjusted_for_user: The ID of the user whose kill count has changed (optional).
    """
    
    current_grudge = user_kills - compare_kills
    #logging.info(f"get_grudge_description: user_id: {user_id}, user_kills: {user_kills}, compare_user: {compare_user}, compare_kills: {compare_kills}, no_article: {no_article}")
    #if the user_id and the compare_user_id are the same, just take the total kills instead of comparing
    if user_id == compare_user:
        kill_count_difference = user_kills
        self_grudge = True
    else: 
        kill_count_difference = user_kills - compare_kills
        self_grudge = False
    #logging.info(f"get_grudge_description: kill_count_difference: {kill_count_difference}")
    #message_content = f"{mention_user(user_id)} has {user_kills} kills. {mention_user(compare_user)} has {compare_kills} kills.\n"

    if self_grudge:
        return f"Your grudge against yourself is ({user_kills}) deep."

    # Find the appropriate descriptor
    descriptor = db.get_grudge_string(user_id, user_kills, compare_user, compare_kills, no_article)
    grudge_holder = get_user_name(raw_request, compare_user if kill_count_difference > 0 else user_id)
    grudge_target = get_user_name(raw_request, user_id if kill_count_difference > 0 else compare_user)

    # Add some variability to the counter-norm phrases
    counter_norm_phrases = [
        "Despite this,",
        "Still,",
        "That said,",
        "Nevertheless,"
    ]
    """
    if counter_norm:
        counter_norm_phrase = random.choice(counter_norm_phrases)
        return f"{counter_norm_phrase} {grudge_holder} still has {descriptor} against {grudge_target}."
    else:
        return f"{grudge_holder} now has {descriptor} against {grudge_target}."
    """
    final_string = f"{grudge_holder} now has {descriptor} against {grudge_target}."
    
    logging.info(f"get_grudge_description: final_string: {final_string}")
    return final_string
def get_grudge_announcement():
    # Category 1: Grudge-related words
    category_1 = [
        "BEEF", "HOSTILITIES", "GRUDGE", "FEUD", "RIVALRY", "BAD BLOOD", "TENSION", 
        "CONFLICT", "VENDETTA", "ANIMOSITIES"
    ]

    # Category 2: Action-related words
    category_2 = [
        "DEEPENED", "EXACERBATED", "ESCALATED", "FUELED", 
        "AMPLIFIED", "INTENSIFIED", "INFLAMED"
    ]

    # Randomly choose one word from each category
    word1 = random.choice(category_1)
    word2 = random.choice(category_2)
    
    # Construct the announcement
    return f"{word1} {word2}!"
def start_message_step_function(raw_request, messages = None, embed = None, follow_up_messages=None, remove_all_buttons=False, ephemeral=False, button_data=None):
    """
    Starts the AWS Step Function to handle message sending.
    
    :param raw_request: Original interaction data (should contain application_id, token, id, etc.)
    :param messages: List of initial messages to send.
    :param follow_up_messages: List of follow-up messages to send.
    :param remove_all_buttons: Flag indicating whether to remove buttons after the initial message.
    :param ephemeral: Flag for ephemeral messages.
    :param button_data: Optional button configuration data.
    """
    # Extract necessary details from raw_request
    application_id = raw_request['application_id']
    interaction_token = raw_request['token']
    interaction_id = raw_request['id']
    message_id = raw_request['message']['id']

    # Get the Step Function ARN from environment variables
    STEP_FUNCTION_ARN = os.environ.get("STEP_FUNCTION_ARN")

    # Initialize AWS Step Functions client
    stepfunctions_client = boto3.client('stepfunctions')
    
    logging.info(f"STARTING STEP FUNCTION: {STEP_FUNCTION_ARN}")
    
    # Prepare the payload for the Step Function
    step_function_payload = {
        'application_id': application_id,
        'interaction_token': interaction_token,
        'id': interaction_id,
        'message_id': message_id,
        'remove_all_buttons': remove_all_buttons,
        'ephemeral': ephemeral,
        'button_data': button_data,
        'embeds': embed
    }
    
    # Send initial messages
    step_function_payload['messages'] = messages
    step_function_payload['followup'] = False  # Initial messages
    stepfunctions_client.start_execution(
        stateMachineArn=STEP_FUNCTION_ARN,
        input=json.dumps(step_function_payload)
    )
    
    # If follow-up messages are provided, send them in a separate invocation
    if follow_up_messages:
        followup_payload = step_function_payload.copy()
        followup_payload['messages'] = follow_up_messages
        followup_payload['followup'] = True  # This is a follow-up message
        stepfunctions_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            input=json.dumps(followup_payload)
        )
def is_valid_json(data):
    try:
        json.loads(data)
        return True
    except json.JSONDecodeError:
        return False
def handle_component_interaction(raw_request, active_entitlement):
    data = raw_request["data"]
    custom_id = data["custom_id"]
    user_id = raw_request["member"]["user"]["id"]
    
    if custom_id.startswith("hello_button:"):
        allowed_user_id = custom_id.split(":")[1]
        
        if user_id == allowed_user_id:
            messages = ["Hello! This is a follow-up message."]
            start_message_step_function(raw_request, messages)
            print(f"Right user found!")
            return {
                "type": 4,
                "data": {
                    "content": "Hello button clicked!"
                }
            }    
        else:
            return jsonify({
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": "Sorry, you're not allowed to use this button.",
                    "flags": 64  # EPHEMERAL - only visible to the user who clicked
                }
            })        
    elif custom_id.startswith("grudgereport_pagination_"):
        # Parse the custom_id to extract necessary information
        _, __, user1, user2, page = custom_id.split("_")
        page = int(page)
        #logging.info(f"Pagination requested for {user1} and {user2} at page {page}")
        custom_footer = None if active_entitlement else "Unlock GrudgeKeeper Premium to browse grudges."
        report, has_more = db.generate_grudge_report(user1, user2, 8, page, raw_request["guild_id"], active_entitlement, custom_footer)

        if not active_entitlement:
            components = [               
                {
                    "type": 1,  # ACTION_ROW
                    "components": [
                        {
                            "type": 2,  # BUTTON
                            "style": 1,  # PRIMARY
                            "label": "Older",
                            "custom_id": f"grudgereport_pagination_{user1}_{user2}_{page}"
                        },
                        {
                            "type": 2,  # BUTTON
                            "style": 6,  # PRIMARY
                            "sku_id": "1296369498529730622"
                        }
                    ]
                }
            ]
            
            response_data = {
                "type": 7,
                "data": {
                    "embeds": [report],
                    "components": components
                }
            }
            #logging.info(f"NON-PREMIUM Pagination response: {response_data}")
            return response_data
        

        components = []
        if has_more:
            components = [               
                {
                    "type": 1,  # ACTION_ROW
                    "components": [
                        {
                            "type": 2,  # BUTTON
                            "style": 1,  # PRIMARY
                            "label": "Older",
                            "custom_id": f"grudgereport_pagination_{user1}_{user2}_{page+1}"
                        },
                        {
                            "type": 2,  # BUTTON
                            "style": 1,  # PRIMARY
                            "label": "Newer",
                            "custom_id": f"grudgereport_pagination_{user1}_{user2}_{page-1}",
                            "disabled": page == 0  # Disable if it's the first page
                        }
                    ]
                }
            ]

        response_data = {
            "type": 7,  # CHANNEL_MESSAGE_WITH_SOURCE
            "data": {
                "embeds": [report],
                "components": components
            }
        }
        logging.info(f"Pagination response: {response_data}")
        return response_data    
    elif custom_id.startswith("forgive_") or custom_id.startswith("grudge_"):
        logger.info(f"{custom_id}")
        custom_id_list = custom_id.split("_")
        #killer_id = custom_id_list[1]
        victim_id = custom_id_list[2]
        #timestamp = custom_id_list[3]

        if user_id == victim_id:
            # Process forgiveness immediately
            
            handle_forgive_button(raw_request, active_entitlement)
            return jsonify({
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": "Forgiveness processed.",
                    "flags": 64  # EPHEMERAL
                }
            })
        else:
            return "This isn't your grudge to forgive."
def interpret_boolean_input(user_input=None, default_value=False) -> bool:
    # Define broad range of inputs for yes and no
    yes_responses = {"y", "ya", "yes", "ye", "yah", "yep", "yup", "yse", "yeah", "yass", "yas", "YES"}
    no_responses = {"n", "no.", "no", "nah", "nope", "non", "nay", "na", "NO", "on"}  # Include 'on' for common typo

    # Check if the input is None or not a string
    if not isinstance(user_input, str):
        return default_value

    # Remove punctuation using str.translate
    user_input_no_punctuation = user_input.translate(str.maketrans('', '', string.punctuation))

    # Normalize the user input (convert to lowercase, strip spaces)
    normalized_input = user_input_no_punctuation.strip().lower()

    # Check for empty input
    if normalized_input == "":
        return default_value

    # Check if the input is in the yes or no sets
    if normalized_input in yes_responses:
        return True
    elif normalized_input in no_responses:
        return False
    else:
        # Return the default value if input is unrecognized
        return default_value