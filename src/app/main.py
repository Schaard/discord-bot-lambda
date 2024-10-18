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

@app.route("/", methods=["POST"])
async def interactions():
    print(f"👉 Request: {request.json}")
    raw_request = request.json

    entitlements = raw_request.get('entitlements', [])
    guild_id = raw_request['guild_id']  # Get the guild ID from the interaction
    sku_id = '1296369498529730622'  

    # Check for active entitlement
    if has_active_entitlement(guild_id, sku_id, entitlements):
        logging.info("Active entitlement found. PREMIUM MODE ENABLED")
    else:
        logging.info("No active entitlement found.")
    
    final_response = interact(raw_request)
    print(f"👈 Response: {final_response.json}")
    return final_response
def remove_article(description):
    articles = ["a ", "an "]  # The articles to check for
    for article in articles:
        if description.startswith(article):
            return description[len(article):]  # Remove the article
    return description
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
        #logging.info(f"Counter-norm movement: {counter_norm} + {previous_grudge} + user: {kill_adjusted_for_user}")
    elif kill_adjusted_for_user == compare_user:
        previous_grudge = user_kills - (compare_kills - 1)  # Adjust for compare_user's kill
        counter_norm = previous_grudge > current_grudge and current_grudge <= -1
        #logging.info(f"Counter-norm movement: {counter_norm} + {previous_grudge} + compare_user: {kill_adjusted_for_user}")
    else:
        previous_grudge = user_kills - compare_kills  # No kill adjustment
        counter_norm = False
        #logging.info(f"Counter-norm movement: {counter_norm} + {previous_grudge} + unfound kill adjusting user: {kill_adjusted_for_user}")
    

    #if the user_id and the compare_user_id are the same, just take the total kills instead of comparing
    if user_id == compare_user:
        kill_count_difference = user_kills
        self_grudge = True
    else: 
        kill_count_difference = user_kills - compare_kills
        self_grudge = False

    #message_content = f"{mention_user(user_id)} has {user_kills} kills. {mention_user(compare_user)} has {compare_kills} kills.\n"

    if self_grudge:
        return f"No grudge detected: both users are tied in their unforgiven kills on each other ({user_kills})."

    # Find the appropriate descriptor
    descriptor = db.get_grudge_string(user_id, user_kills, compare_user, compare_kills, no_article)

    grudge_target = get_user_name(raw_request, compare_user if kill_count_difference > 0 else user_id)
    grudge_holder = get_user_name(raw_request, user_id if kill_count_difference > 0 else compare_user)

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
    return f"{grudge_holder} now has {descriptor} against {grudge_target}."
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
    
    #logging.info(f"STARTING STEP FUNCTION: {STEP_FUNCTION_ARN}")
    
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
    victim_name = get_name_fromid(victim)
    user_name = get_name_fromid(user_id)
    if _ == "forgive":
        forgiveness_message = f"{victim_name} has forgiven {mention_user(user_id)}'s kill on {pretty_timestamp}."
        # Use the parsed information to mark the specific kill as forgiven in the database
        db.forgive_kill(user_id, victim, timestamp)
        new_grudge = db.get_grudge_string(user_id, db.get_unforgivencount_on_user(user_id, victim), victim, db.get_unforgivencount_on_user(victim, user_id), False)
        forgiveness_message += f"\n{victim_name}'s grudge against {user_name} is now {new_grudge}"
    elif _ == "grudge":
        forgivee_name = f"{mention_user(user_id)}" if self_forgive == False else "themselves"
        forgiveness_message = f"{victim_name} will never forgive {forgivee_name}."
    

    start_message_step_function(raw_request, [forgiveness_message], [], True)    
def is_valid_json(data):
    try:
        json.loads(data)
        return True
    except json.JSONDecodeError:
        return False
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
    elif custom_id.startswith("grudgereport_pagination_"):
        # Parse the custom_id to extract necessary information
        _, __, user1, user2, page = custom_id.split("_")
        page = int(page)
        #logging.info(f"Pagination requested for {user1} and {user2} at page {page}")
        report, has_more = db.generate_grudge_report(user1, user2, 8, page)
        
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
            
            handle_forgive_button(raw_request)
            return jsonify({
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": "Forgiveness processed.",
                    "flags": 64  # EPHEMERAL
                }
            })
        else:
            return "This isn't your grudge."
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
                case "report":
                    # Generate a monthly report for the server (guild)
                    server_id = str(raw_request["guild_id"])
                    # Set the time range for the current month
                    today = datetime.utcnow()

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
                    monthly_report = db.get_wrapped_report(server_id, first_day_of_month, last_day_of_month)

                    # Return the report as a message to the channel
                    response_data = {
                        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                        "data": {
                            "content": monthly_report
                        }
                    }
                    return jsonify(response_data)                
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
                                            "placeholder": "What was said over voice chat?",
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
                                            "placeholder": "What was said over voice chat?",
                                            "required": False
                                        }
                                    ]
                                },
                            ]
                        }
                    }
                    return jsonify(response_data)
                case "grudges":
                    try:
                        options = data.get("options", [])
                        page = 0  # Default to first page
                        logging.info(f"Number of options: {len(options)}")
                        grudge_depth = 8
                        if len(options) == 1:
                            # Report between calling user and specified user
                            target_user = options[0]["value"]
                            user1 = user_id
                            user2 = target_user
                            report, has_more = db.generate_grudge_report(user_id, target_user, grudge_depth)
                        elif len(options) == 2:
                            # Report between two specified users
                            user1 = options[0]["value"]
                            user2 = options[1]["value"]
                            report, has_more = db.generate_grudge_report(user1, user2, grudge_depth)
                        else:
                            raise ValueError("Invalid number of arguments for grudgereport")
                        #logging.info(f"Grudge report generated: {report}")
                        
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
                                            "custom_id": f"grudgereport_pagination_{user1}_{user2}_{page+1}"
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
                    
                    return jsonify(response_data)
                case "hallofshame":
                    try:
                        top_killers = db.get_top_killers(limit=5)  # Get top 5 killers
                        if top_killers:
                            message_content = "🏆 Hall of Shame 🏆\n Players with the most unforgiven kills.\n"
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
                    victim = parts[3] # Extract the victim ID from the custom_id
                    user_id = parts[2]  # Extract the user ID from the custom_id

                    # Process other modal inputs
                    cause_of_death = data["components"][0]["components"][0]["value"]
                    cause_of_death = sanitize_input(cause_of_death)
                    last_words = data["components"][1]["components"][0]["value"]
                    last_words = sanitize_input(last_words)
                    #unforgivable = data["components"][2]["components"][0]["value"]
                    #unforgivable = interpret_boolean_input(unforgivable)
                    
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
                        db.add_kill(user_id, user_id, victim, cause_of_death, server_id, game_id, channel_id, timestamp, False, forgiven)

                        # Construct the message_content dynamically
                        if cause_of_death is None or cause_of_death == "":
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)}!"
                        else:
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)} by {cause_of_death}!"

                        if last_words:
                            content_for_kill_message += f' Their last words were: "{last_words}"'

                        #if unforgivable:
                        #    content_for_kill_message += " This grudge has been marked UNFORGIVABLE!"

                        #if not unforgivable and forgiven:
                        #    content_for_kill_message += f" {get_name_fromid(victim)} forgave them instantly."

                        user_kills = db.get_unforgivencount_on_user(user_id, victim)
                        compare_kills = db.get_unforgivencount_on_user(victim, user_id)
                        user_name = get_user_name(raw_request, victim)
                        victim_name = get_user_name(raw_request, user_id)
                        end_of_kill_message = f"{get_grudge_description(raw_request, user_id, user_kills, victim, compare_kills, False, victim)}"                                                
                        
                        if user_kills > compare_kills:
                            content_for_kill_message += f"\nWith {user_kills} unforgiven kills on {victim_name} and only {compare_kills} in return, {end_of_kill_message}"
                        else:
                            content_for_kill_message += f"\nWith {compare_kills} unforgiven kills on {user_name} and only {user_kills} in return, {end_of_kill_message}"
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
                                                "label": "Forgive (-1 Grudge)",  # Supportive and positive action
                                                "style": 1,  # Green button (Success)
                                                "custom_id": f"forgive_{user_id}_{victim}_{timestamp}"
                                            },
                                            {
                                                "type": 2,  # Button
                                                "label": "Do Not Forgive",  # Not forgiving action
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
                    cause_of_death = sanitize_input(cause_of_death)
                    last_words = data["components"][1]["components"][0]["value"]
                    last_words = sanitize_input(last_words)
                    #unforgivable = data["components"][2]["components"][0]["value"]
                    #unforgivable = interpret_boolean_input(unforgivable)
                    forgiven = False
                    #forgiven = interpret_boolean_input(forgiven)
                    
                    # Retrieve the server, game, and channel IDs
                    server_id = str(raw_request["guild_id"])
                    game_id = "default_game_id"  # Replace with the actual game ID
                    channel_id = str(raw_request["channel_id"])

                    # Get the current UTC time and format it as ISO 8601 string
                    timestamp = datetime.utcnow().isoformat()

                    # Now you can use the victim ID along with other modal input data
                    try:
                        db.add_kill(user_id, user_id, victim, cause_of_death, server_id, game_id, channel_id, timestamp, False, forgiven)

                        # Construct the message_content dynamically
                        if cause_of_death is None or cause_of_death == "":
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)}!"
                        else:
                            content_for_kill_message = f"{get_grudge_announcement()} {mention_user(user_id)} killed {mention_user(victim)} by {cause_of_death}!"

                        if last_words:
                            content_for_kill_message += f' Their last words were: "{last_words}"'

                        #if unforgivable:
                        #    content_for_kill_message += " This grudge has been marked UNFORGIVABLE!"

                        #if not unforgivable and forgiven:
                        #    content_for_kill_message += f" {get_name_fromid(victim)} forgave them instantly."

                        user_kills = db.get_unforgivencount_on_user(user_id, victim)
                        compare_kills = db.get_unforgivencount_on_user(victim, user_id)
                        user_name = get_user_name(raw_request, victim)
                        victim_name = get_user_name(raw_request, user_id)
                        
                        end_of_kill_message = f"{get_grudge_description(raw_request, user_id, user_kills, victim, compare_kills, False, victim)}"

                        if user_kills > compare_kills:
                            content_for_kill_message += f"\nWith {user_kills} unforgiven kills on {victim_name} and only {compare_kills} in return, {end_of_kill_message}"
                        else:
                            content_for_kill_message += f"\nWith {compare_kills} unforgiven kills on {user_name} and only {user_kills} in return, {end_of_kill_message}"

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
                                                "label": "Forgive (-1 Grudge)",  # Supportive and positive action
                                                "style": 1,  # Green button (Success)
                                                "custom_id": f"forgive_{user_id}_{victim}_{timestamp}"
                                            },
                                            {
                                                "type": 2,  # Button
                                                "label": "Do Not Forgive",  # Not forgiving action
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