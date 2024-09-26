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
from datetime import datetime

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
dbname = os.environ.get("DYNAMODB_TABLE_NAME")
db = DynamoDBHandler(os.environ.get("DYNAMODB_TABLE_NAME"))
DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")

def mention_user(user_id):
    return f"<@{user_id}>"

@app.route("/", methods=["POST"])
async def interactions():
    print(f"👉 Request: {request.json}")
    raw_request = request.json
    final_response = interact(raw_request)
    print(f"👈 Response: {final_response}")
    return final_response

def get_grudge_description(user_id, user_kills, compare_user, compare_kills):
    kill_count_difference = user_kills - compare_kills

    #message_content = f"{mention_user(user_id)} has {user_kills} kills. {mention_user(compare_user)} has {compare_kills} kills.\n"

    lead_descriptors = {
        0: "😇 no grudge 😇",
        1: "🌱 a budding grudge 🌱",
        2: "🙈 a double grudge 🙈",
        3: "😬 a triple grudge 😬",
        4: "🔥 a QUADRUPLE grudge 🔥",
        5: "💥 a PENTAGRUDGE 💥",
        6: "👹 a MONSTER GRUDGE 👹",
        10: "⚡ an OMEGA SUPER GRUDGE ⚡",
        15: "⏳ an ETERNAL GRUDGE ⏳",
        20: "🚀 a DOUBLE-ETERNAL INTERSOLAR GIGAGRUDGE 🚀",
        25: "💫 a grudge whose magnitude exceeds conceptualization 💫",
        30: "💔 a grudge so intense and painful that it is more like love 💔",
        35: "🧨 a CATASTROPHIC grudge 🧨",
        40: "🌋 a grudge of apocalyptic proportions 🌋",
        45: "🦖 a PREHISTORIC grudge that refuses to go extinct 🦖",
        50: "🏰 GRUDGEHOLDE: an imposing stronghold built of pure grudge 🏰",
        60: "🌪️ a MEGA-TORNADO grudge that uproots everything 🌪️",
        65: "🕵️‍♂️ a grudge that is currently under investigation 🕵️‍♂️",
        70: "👑 a ROYAL grudge demanding fealty from all lesser grudges 👑",
        75: "🚨 a GRUDGE-LEVEL RED (emergency protocols activated) 🚨",
        80: "🧬 a GENETICALLY ENGINEERED SUPER GRUDGE 🧬",
        85: "📜 an ANCIENT GRUDGE, foretold in portents unseen, inscribed in the stars themselves 📜",
        90: "🕳️ an ALL-CONSUMING black hole of grudges, drawing other, smaller grudges to itself, incorporating them into its power for a purpose unfathomable by the primitive and imprecise organic shambling that is the feeble human brain 🕳️",
        95: "🌌 a COSMIC GRUDGE spanning the entire grudgepast, grudgepresent, and grudgefuture 🌌",
        100: "👾 a GOD-TIER allgrudge transcending grudgespace and grudgetime 👾"
    }

    for threshold, descriptor in sorted(lead_descriptors.items(), reverse=True):
        if abs(kill_count_difference) >= threshold:
            if kill_count_difference >= 0:
                message_content = f"{mention_user(compare_user)} has {descriptor} against {mention_user(user_id)} (+{kill_count_difference})."
            elif kill_count_difference < 0:
                message_content = f"{mention_user(user_id)} has {descriptor} against {mention_user(compare_user)} (+{abs(kill_count_difference)})."
            break
    else:
        message_content = "Both users are tied in their kill counts. No grudge detected. "
    return message_content

def start_message_step_function(raw_request, messages, follow_up_messages, remove_all_buttons = False):
    # Initialize AWS Step Functions client
    application_id = raw_request['application_id']
    interaction_token = raw_request['token']
    interaction_id = raw_request['id']
    message_id = raw_request['message']['id']

    STEP_FUNCTION_ARN = os.environ.get("STEP_FUNCTION_ARN")
    stepfunctions_client = boto3.client('stepfunctions')
    logging.info(f"STARTING STEP FUNCTION: {STEP_FUNCTION_ARN}")
    stepfunctions_client.start_execution(
        stateMachineArn=STEP_FUNCTION_ARN,
        input=json.dumps({
            'application_id': application_id,
            'interaction_token': interaction_token,
            'messages': messages,
            'follow_up_messages' : follow_up_messages,
            'id' : interaction_id,
            'message_id' : message_id,
            'remove_all_buttons' : remove_all_buttons
        })
    )

def handle_forgive_button(raw_request):
    # Extract the custom_id from the interaction
    custom_id = raw_request['data']['custom_id']
    
    # Parse the custom_id to get the relevant fields
    _, user_id, victim, timestamp = custom_id.split('_')

    # Use the parsed information to mark the specific kill as forgiven in the database
    db.forgive_kill(user_id, victim, timestamp)
    forgiveness_message = f"{mention_user(user_id)} has forgiven {mention_user(victim)}'s kill on {timestamp}."
    start_message_step_function(raw_request, [forgiveness_message], [], True)
    
def handle_component_interaction(raw_request):
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
        
    elif custom_id.startswith("forgive_"):
        logger.info(f"{custom_id}")
        custom_id_list = custom_id.split("_")
        #killer_id = custom_id_list[1]
        victim_id = custom_id_list[2]
        #timestamp = custom_id_list[3]

        if user_id == victim_id:
            # Process forgiveness immediately
            
            handle_forgive_button(raw_request)
            return jsonify({
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": "Forgiveness processed. The original message has been updated.",
                    "flags": 64  # EPHEMERAL
                }
            })
        else:
            return "This grudge isn't yours to forgive."

@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interact(raw_request):
    if raw_request["type"] == 1:  # PING
        return jsonify({"type": 1}) # PONG
           
    match raw_request["type"]:
        case 2:  # APPLICATION_COMMAND
            data = raw_request["data"]
            command_name = data["name"]
            logger.info("Application command received")
            user_id = raw_request["member"]["user"]["id"]
            
            match command_name:
                case "hello":
                    message_content = "Hello there!!!!!"
                    
                    # Create a response with a button
                    response_data = {
                        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                        "data": {
                            "content": message_content,
                            "components": [
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 2,  # BUTTON
                                            "label": "Hello!",
                                            "style": 1,  # PRIMARY
                                            "custom_id": f"hello_button:{user_id}"
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                    print(f"{response_data}")
                    print(f"{jsonify(response_data)}")
                    return jsonify(response_data)
                case "echo":
                    original_message = data["options"][0]["value"]
                    message_content = f"Echoing: {original_message}"
                case "oops":
                    victim = data["options"][0]["value"]
                    cause_of_death = data["options"][1]["value"] if len(data["options"]) > 1 else "unknown"
                    last_words = data["options"][2]["value"] if len(data["options"]) > 2 else None
                    unforgivable = data["options"][3]["value"] if len(data["options"]) > 3 else False
                    forgiven = data["options"][4]["value"] if len(data["options"]) > 4 else False

                    # Retrieve the server, game, and channel IDs
                    server_id = str(data["guild_id"])
                    game_id = "default_game_id"  # Replace with the actual game ID
                    channel_id = str(raw_request["channel_id"])
                    
                    # Get the current UTC time and format it as ISO 8601 string
                    timestamp = datetime.utcnow().isoformat()

                    try:
                        db.add_kill(user_id, user_id, victim, cause_of_death, server_id, game_id, channel_id, timestamp, unforgivable, forgiven)

                        # Construct the message_content dynamically
                        content_for_kill_message = f"Oops! {mention_user(user_id)} killed {mention_user(victim)} by {cause_of_death}."

                        if last_words:
                            content_for_kill_message += f' Their last words were: "{last_words}"'

                        if unforgivable:
                            content_for_kill_message += " This kill is unforgivable!"

                        if forgiven:
                            content_for_kill_message += " But it has been forgiven."

                        user_kills = db.get_unforgivencount_on_user(user_id, victim)
                        compare_kills = db.get_unforgivencount_on_user(victim, user_id)
                        
                        content_for_kill_message += f"\n{get_grudge_description(user_id, user_kills, victim, compare_kills)}"

                        # Create a response with a button
                        response_data = {
                            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                            "data": {
                                "content": content_for_kill_message,
                                "components": [
                                    {
                                        "type": 1,  # ACTION_ROW
                                        "components": [
                                            {
                                                "type": 2,  # Button
                                                "label": "Forgive",
                                                "style": 1,
                                                "custom_id": f"forgive_{user_id}_{victim}_{timestamp}"
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                        return jsonify(response_data)
                    except Exception as e:
                        message_content = f"Error recording oops: {str(e)}"
                    
                case "ettu":
                    betrayer = data["options"][0]["value"]
                    murder_weapon = data["options"][1]["value"] if len(data["options"]) > 1 else "unknown"
                    last_words = data["options"][2]["value"] if len(data["options"]) > 2 else None
                    unforgivable = data["options"][3]["value"] if len(data["options"]) > 3 else False
                    forgiven = data["options"][4]["value"] if len(data["options"]) > 4 else False

                    # Get the current UTC time and format it as ISO 8601 string
                    timestamp = datetime.utcnow().isoformat()

                    # Retrieve the server, game, and channel IDs
                    server_id = str(data["guild_id"])
                    game_id = "default_game_id"  # Replace with the actual game ID
                    channel_id = str(raw_request["channel_id"])
                    
                    try:
                        db.add_kill(betrayer, betrayer, user_id, murder_weapon, server_id, game_id, channel_id, timestamp, unforgivable, forgiven)

                        # Construct the message_content dynamically
                        if murder_weapon != "unknown":
                            message_content = f"Et tu, {mention_user(betrayer)}? Then fall, {mention_user(user_id)} (by {murder_weapon})!"
                        else:
                            message_content = f"Et tu, {mention_user(betrayer)}? Then fall, {mention_user(user_id)}!"

                        if last_words:
                            message_content += f" {mention_user(user_id)}'s last words: '{last_words}'"

                        if unforgivable:
                            message_content += " This kill is unforgivable!"

                        if forgiven:
                            message_content += " But it has been forgiven."
                        
                        user_kills = db.get_kill_count(user_id)
                        compare_kills = db.get_kill_count(betrayer)
                        message_content += f"\n{get_grudge_description(user_id, user_kills, betrayer, compare_kills)}"
                    except Exception as e:
                        message_content = f"Error recording betrayal: {str(e)}"
                case "undoops":
                    try:
                        removed_command = db.remove_latest_command(user_id)
                        if removed_command:
                            killer_id = removed_command['KillerUserId']
                            victim_id = removed_command['TargetUserId']
                            cause_of_death = removed_command['CauseOfDeath']
                            if killer_id == user_id:
                                message_content = f"Undid your latest oops! {mention_user(killer_id)} no longer killed {mention_user(victim_id)} by {cause_of_death}."
                            else:
                                message_content = f"Undid your latest ettu! {mention_user(killer_id)} no longer killed you by {cause_of_death}."
                        else:
                            message_content = f"No recent commands found for {mention_user(user_id)} to undo."
                    except Exception as e:
                        message_content = f"Error undoing command: {str(e)}"
                case "grudge":
                    compare_user = data["options"][0]["value"]
                    try:
                        user_kills = db.get_kill_count(user_id)
                        compare_kills = db.get_kill_count(compare_user)
                        message_content = f"{mention_user(user_id)} has {user_kills} kills. {mention_user(compare_user)} has {compare_kills} kills.\n"
                        message_content += get_grudge_description(user_id, user_kills, compare_user, compare_kills)
                    except Exception as e:
                        message_content = f"Error comparing kill counts: {str(e)}"
                case "hallofshame":
                    try:
                        top_killers = db.get_top_killers(limit=5)  # Get top 5 killers
                        if top_killers:
                            message_content = "🏆 Hall of Shame 🏆\n"
                            for i, (killer_id, kill_count) in enumerate(top_killers, 1):
                                message_content += f"{i}. {mention_user(killer_id)}: {kill_count} kills\n"
                        else:
                            message_content = "The Hall of Shame is empty. Be the first to make a mistake!"
                    except Exception as e:
                        message_content = f"Error retrieving Hall of Shame: {str(e)}"
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
            result = handle_component_interaction(raw_request)
            if isinstance(result, str):
                return jsonify({
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": result,
                    "flags": 64  # EPHEMERAL
                }
            })
            
            #If not string, Respond immediately with 202 Accepted
            response = Response('', 202)
            return response            
        case 4:  # APPLICATION_COMMAND_AUTOCOMPLETE
            logger.info("Autocomplete received")
        case 5:  # MODAL_SUBMIT
            logger.info("Modal submit received")