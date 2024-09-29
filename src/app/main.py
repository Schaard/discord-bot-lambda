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
import requests
import random
import re
import string

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
    
def get_user_name(raw_request, user_id):
    #print the user name 
    try:
        user_info = raw_request['data']['resolved']['users'][f"{user_id}"]["username"]
    except Exception as e:
        logger.error(f"Name not found in raw_request: {e}")
        user_info = get_name_fromid(user_id)
    
    return user_info

@app.route("/", methods=["POST"])
async def interactions():
    print(f"👉 Request: {request.json}")
    raw_request = request.json
    final_response = interact(raw_request)
    print(f"👈 Response: {final_response}")
    return final_response

def remove_article(description):
    articles = ["a ", "an "]  # The articles to check for
    for article in articles:
        if description.startswith(article):
            return description[len(article):]  # Remove the article
    return description
def get_grudge_string(raw_request, user_id, user_kills, compare_user, compare_kills, no_article = False):
    #if the user_id and the compare_user_id are the same, just take the total kills instead of comparing
    
    if user_id == compare_user:
        kill_count_difference = user_kills
        self_grudge = True
    else: 
        kill_count_difference = user_kills - compare_kills
        self_grudge = False

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

    if not self_grudge:
        for threshold, descriptor in sorted(lead_descriptors.items(), reverse=True):
            if abs(kill_count_difference) >= threshold:
                if kill_count_difference >= 0:
                    grudge_descriptor = descriptor
                elif kill_count_difference < 0:
                    grudge_descriptor = descriptor
                break
    else: 
        for threshold, descriptor in sorted(lead_descriptors.items(), reverse=True):
            if abs(kill_count_difference) >= threshold:
                if kill_count_difference >= 0:
                    grudge_descriptor = descriptor
                elif kill_count_difference < 0:
                    grudge_descriptor = descriptor
                break
    
    # Optionally remove the article
    if no_article:
        grudge_descriptor = remove_article(grudge_descriptor)

    return grudge_descriptor
def get_grudge_description(raw_request, user_id, user_kills, compare_user, compare_kills, no_article = False, kill_adjusted_for_user=None):
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

    # Calculate previous grudge based on who committed the kill
    if kill_adjusted_for_user == user_id:
        previous_grudge = (user_kills - 1) - compare_kills  # Adjust for user_id's kill
        counter_norm = previous_grudge < current_grudge and current_grudge >= 1
        logging.info(f"Counter-norm movement: {counter_norm} + {previous_grudge} + user: {kill_adjusted_for_user}")
    elif kill_adjusted_for_user == compare_user:
        previous_grudge = user_kills - (compare_kills - 1)  # Adjust for compare_user's kill
        counter_norm = previous_grudge > current_grudge and current_grudge <= -1
        logging.info(f"Counter-norm movement: {counter_norm} + {previous_grudge} + compare_user: {kill_adjusted_for_user}")
    else:
        previous_grudge = user_kills - compare_kills  # No kill adjustment
        counter_norm = False
        logging.info(f"Counter-norm movement: {counter_norm} + {previous_grudge} + unfound kill adjusting user: {kill_adjusted_for_user}")
    

    #if the user_id and the compare_user_id are the same, just take the total kills instead of comparing
    if user_id == compare_user:
        kill_count_difference = user_kills
        self_grudge = True
    else: 
        kill_count_difference = user_kills - compare_kills
        self_grudge = False

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


    # Add some variability to the counter-norm phrases
    counter_norm_phrases = [
        "Despite this,",
        "Still,",
        "That said,",
        "Nevertheless,"
    ]

    if not self_grudge:
        for threshold, descriptor in sorted(lead_descriptors.items(), reverse=True):
            if abs(kill_count_difference) >= threshold:
                if counter_norm:
                    if kill_count_difference >= 0:
                        message_content = f"{random.choice(counter_norm_phrases)} {get_user_name(raw_request, compare_user)} still has {descriptor} against {get_user_name(raw_request, user_id)} (+{abs(kill_count_difference)})."
                    elif kill_count_difference < 0:
                        message_content = f"{random.choice(counter_norm_phrases)} {get_user_name(raw_request, user_id)} still has {descriptor} against {get_user_name(raw_request, compare_user)} (+{abs(kill_count_difference)})."                    
                else:                
                    if kill_count_difference >= 0:
                        message_content = f"{get_user_name(raw_request, compare_user)} now has {descriptor} against {get_user_name(raw_request, user_id)} (+{kill_count_difference})."
                    elif kill_count_difference < 0:
                        message_content = f"{get_user_name(raw_request, user_id)} now has {descriptor} against {get_user_name(raw_request, compare_user)} (+{abs(kill_count_difference)})."
                break
        else:
            message_content = "Both users are tied in their kill counts. No grudge detected. "
    else: 
        for threshold, descriptor in sorted(lead_descriptors.items(), reverse=True):
            if abs(kill_count_difference) >= threshold:
                if kill_count_difference >= 0:
                    message_content = f"{get_user_name(raw_request, compare_user)} has {descriptor} against themselves (+{kill_count_difference})."
                elif kill_count_difference < 0:
                    message_content = f"{get_user_name(raw_request, user_id)} has {descriptor} against themselves (+{abs(kill_count_difference)})."
                break
    
    # Optionally remove the article
    if no_article:
        message_content = remove_article(message_content)

    return message_content
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

def start_message_step_function(raw_request, messages, follow_up_messages=None, remove_all_buttons=False, ephemeral=False, button_data=None):
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
        'button_data': button_data
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

def get_random_forgiveness_message(original_grudge_description, postforgiveness_grudge_description):
    messages = [
        f"Before forgiveness, the grudge stood at: \n**{original_grudge_description}**\n\nAfter this act of mercy, it has now changed to: \n**{postforgiveness_grudge_description}**\n\nBalance is restored, at least for now.",
        
        f"Initially, the grudge was recorded as: \n**{original_grudge_description}**\n\nFollowing forgiveness, it has shifted to: \n**{postforgiveness_grudge_description}**\n\nFor now, the tension has eased.",
        
        f"The grudge was previously assessed at: \n**{original_grudge_description}**\n\nNow, after forgiveness, it has reduced to: \n**{postforgiveness_grudge_description}**\n\nLet’s hope this lasts.",
        
        f"At the outset, the grudge was measured as: \n**{original_grudge_description}**\n\nIn the wake of forgiveness, it is now: \n**{postforgiveness_grudge_description}**\n\nPerhaps harmony can be found.",
        
        f"Before forgiveness, the grudge level was: \n**{original_grudge_description}**\n\nAfter the act of kindness, it has now become: \n**{postforgiveness_grudge_description}**\n\nTime will tell if this change is permanent.",
        
        f"Originally, the grudge was recorded as: \n**{original_grudge_description}**\n\nNow, thanks to forgiveness, it has transformed to: \n**{postforgiveness_grudge_description}**\n\nWill this new state hold?",
        
        f"The grudge's initial status was: \n**{original_grudge_description}**\n\nFollowing forgiveness, it has shifted to: \n**{postforgiveness_grudge_description}**\n\nA new equilibrium has been reached.",
        
        f"Initially, the grudge was classified as: \n**{original_grudge_description}**\n\nNow, post-forgiveness, it is classified as: \n**{postforgiveness_grudge_description}**\n\nLet’s see how this plays out.",
        
        f"The previous grudge status was: \n**{original_grudge_description}**\n\nAfter this moment of mercy, it has changed to: \n**{postforgiveness_grudge_description}**\n\nWill this change hold?",
        
        f"The grudge was initially rated as: \n**{original_grudge_description}**\n\nNow, it has adjusted to: \n**{postforgiveness_grudge_description}**\n\nTime will reveal the outcome."
    ]
    
    return random.choice(messages)


def handle_forgive_button(raw_request):
    # Extract the custom_id from the interaction
    custom_id = raw_request['data']['custom_id']
    
    # Parse the custom_id to get the relevant fields
    _, user_id, victim, timestamp = custom_id.split('_')
    
    #Detect if this is someone with the option to forgive themselves
    self_forgive = True if victim == user_id else False

    
    # Convert the string back to a datetime object
    pretty_timestamp = datetime.fromisoformat(timestamp)
    # Format the timestamp to be more readable
    pretty_timestamp = pretty_timestamp.strftime("%B %d, %Y at %I:%M %p (UTC)")

    if _ == "forgive":
        forgiveness_message = f"{get_name_fromid(victim)} has forgiven {mention_user(user_id)}'s kill on {pretty_timestamp}."
        # Use the parsed information to mark the specific kill as forgiven in the database
        #original_grudge_description = get_grudge_description(raw_request, user_id, db.get_unforgivencount_on_user(user_id, victim), victim, db.get_unforgivencount_on_user(victim, user_id))
        db.forgive_kill(user_id, victim, timestamp)
        #postforgiveness_grudge_description = get_grudge_description(raw_request, user_id, db.get_unforgivencount_on_user(user_id, victim), victim, db.get_unforgivencount_on_user(victim, user_id))
    elif _ == "grudge":
        forgivee_name = f"{mention_user(user_id)}" if self_forgive == False else "themselves"
        forgiveness_message = f"{get_name_fromid(victim)} has refused to forgive {forgivee_name}."
    
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
        
    elif custom_id.startswith("forgive_") or custom_id.startswith("grudge_"):
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

def interpret_boolean_input(user_input: str) -> bool:
    # Define broad range of inputs for yes and no
    yes_responses = {"y", "ya", "yes", "ye", "yah", "yep", "yup", "yse", "yeah", "yass", "yas", "YES"}
    no_responses = {"n", "no.", "no", "nah", "nope", "non", "nay", "na", "NO", "on"}  # Include 'on' since it's a common typo

    # Remove punctuation using str.translate
    user_input_no_punctuation = user_input.translate(str.maketrans('', '', string.punctuation))

    # Normalize the user input (convert to lowercase, strip spaces)
    normalized_input = user_input_no_punctuation.strip().lower()

    # Check for empty input
    if normalized_input == "":
        return False

    # Check if the input is in the yes or no sets
    if normalized_input in yes_responses:
        return True
    elif normalized_input in no_responses:
        return False
    else:
        # You can log a warning or default to False if input is unrecognized
        return False

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
                                            "style": 1,  # Short input
                                            "label": "Cause of Death (optional)",
                                            "placeholder": "What was the cause of death?",
                                            "required": False
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
                                            "placeholder": "Your final words on voice chat",
                                            "required": False
                                        }
                                    ]
                                },
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "unforgivable_input",
                                            "style": 1,  # Short input
                                            "label": "This grudge is UNFORGIVABLE (default: no)",
                                            "placeholder": "No",
                                            "required": False
                                        }
                                    ]
                                },
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "forgiven_input",
                                            "style": 1,  # Short input
                                            "label": "Have you forgiven them? (default: no)",
                                            "placeholder": "No, I'm holding a grudge",
                                            "required": False
                                        }
                                    ]
                                }
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
                                            "style": 1,  # Short input
                                            "label": "Cause of Death (optional)",
                                            "placeholder": "What was the cause of death?",
                                            "required": False
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
                                            "placeholder": "Your victim's last words",
                                            "required": False
                                        }
                                    ]
                                },
                                {
                                    "type": 1,  # ACTION_ROW
                                    "components": [
                                        {
                                            "type": 4,  # TEXT_INPUT
                                            "custom_id": "unforgivable_input",
                                            "style": 1,  # Short input
                                            "label": "This was UNFORGIVABLE (default: no)",
                                            "placeholder": "No",
                                            "required": False
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                    return jsonify(response_data)
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
                case "grudges":
                    compare_user = data["options"][0]["value"]
                    try:
                        user_kills = db.get_kill_count(user_id)
                        compare_kills = db.get_kill_count(compare_user)
                        message_content = f"{mention_user(user_id)} has {user_kills} kills. {mention_user(compare_user)} has {compare_kills} kills.\n"
                        message_content += get_grudge_description(raw_request, user_id, user_kills, compare_user, compare_kills)
                    except Exception as e:
                        message_content = f"Error comparing kill counts: {str(e)}"
                case "hallofshame":
                    try:
                        top_killers = db.get_top_killers(limit=5)  # Get top 5 killers
                        if top_killers:
                            message_content = "🏆 Hall of Shame 🏆\n"
                            for i, (killer_id, kill_count) in enumerate(top_killers, 1):
                                message_content += f"{i}. {get_name_fromid(killer_id)}: {kill_count} kills\n"
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
                    victim = parts[3] # Extract the victim ID from the custom_id
                    user_id = parts[2]  # Extract the user ID from the custom_id

                    # Process other modal inputs
                    cause_of_death = data["components"][0]["components"][0]["value"]
                    last_words = data["components"][1]["components"][0]["value"]
                    unforgivable = data["components"][2]["components"][0]["value"]
                    unforgivable = interpret_boolean_input(unforgivable)
                    
                    #can't forgive your own oops 
                    forgiven = False
                    
                    # Retrieve the server, game, and channel IDs
                    server_id = str(raw_request["guild_id"])
                    game_id = "default_game_id"  # Replace with the actual game ID
                    channel_id = str(raw_request["channel_id"])

                    # Get the current UTC time and format it as ISO 8601 string
                    timestamp = datetime.utcnow().isoformat()

                    # Now you can use the victim ID along with other modal input data
                    try:
                        db.add_kill(user_id, user_id, victim, cause_of_death, server_id, game_id, channel_id, timestamp, unforgivable, forgiven)

                        # Construct the message_content dynamically
                        if cause_of_death is None or cause_of_death == "":
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)}!"
                        else:
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)} by {cause_of_death}!"

                        if last_words:
                            content_for_kill_message += f' Their last words were: "{last_words}"'

                        if unforgivable:
                            content_for_kill_message += " This grudge has been marked UNFORGIVABLE!"

                        if not unforgivable and forgiven:
                            content_for_kill_message += f" {get_name_fromid(victim)} forgave them instantly."

                        user_kills = db.get_unforgivencount_on_user(user_id, victim)
                        compare_kills = db.get_unforgivencount_on_user(victim, user_id)
                        
                        content_for_kill_message += f"\n{get_grudge_description(raw_request, user_id, user_kills, victim, compare_kills, False, user_id)}"

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
                                                "label": "Forgive",  # Supportive and positive action
                                                "style": 3,  # Green button (Success)
                                                "custom_id": f"forgive_{user_id}_{victim}_{timestamp}"
                                            },
                                            {
                                                "type": 2,  # Button
                                                "label": "Do Not Forgive (+1 Grudge)",  # Not forgiving action
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
                    victim = parts[2] # Extract the victim ID from the custom_id
                    user_id = parts[3]  # Extract the user ID from the custom_id

                    # Process other modal inputs
                    cause_of_death = data["components"][0]["components"][0]["value"]
                    last_words = data["components"][1]["components"][0]["value"]
                    unforgivable = data["components"][2]["components"][0]["value"]
                    unforgivable = interpret_boolean_input(unforgivable)
                    forgiven = data["components"][3]["components"][0]["value"]
                    forgiven = interpret_boolean_input(forgiven)
                    
                    # Retrieve the server, game, and channel IDs
                    server_id = str(raw_request["guild_id"])
                    game_id = "default_game_id"  # Replace with the actual game ID
                    channel_id = str(raw_request["channel_id"])

                    # Get the current UTC time and format it as ISO 8601 string
                    timestamp = datetime.utcnow().isoformat()

                    # Now you can use the victim ID along with other modal input data
                    try:
                        db.add_kill(user_id, user_id, victim, cause_of_death, server_id, game_id, channel_id, timestamp, unforgivable, forgiven)

                        # Construct the message_content dynamically
                        if cause_of_death is None or cause_of_death == "":
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)}!"
                        else:
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)} by {cause_of_death}!"

                        if last_words:
                            content_for_kill_message += f' Their last words were: "{last_words}"'

                        if unforgivable:
                            content_for_kill_message += " This grudge has been marked UNFORGIVABLE!"

                        if not unforgivable and forgiven:
                            content_for_kill_message += f" {get_name_fromid(victim)} forgave them instantly."

                        user_kills = db.get_unforgivencount_on_user(user_id, victim)
                        compare_kills = db.get_unforgivencount_on_user(victim, user_id)
                        
                        content_for_kill_message += f"\n{get_grudge_description(raw_request, user_id, user_kills, victim, compare_kills, False, victim)}"

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
                                                "label": "Forgive",  # Supportive and positive action
                                                "style": 3,  # Green button (Success)
                                                "custom_id": f"forgive_{user_id}_{victim}_{timestamp}"
                                            },
                                            {
                                                "type": 2,  # Button
                                                "label": "Do Not Forgive (+1 Grudge)",  # Not forgiving action
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