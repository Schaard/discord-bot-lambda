import os
import logging
from flask import Flask, jsonify, request
from mangum import Mangum
from asgiref.wsgi import WsgiToAsgi
from discord_interactions import verify_key_decorator
from database import DynamoDBHandler
from dotenv import load_dotenv

#set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Load environment variables from .env file
load_dotenv()

DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")
app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
handler = Mangum(asgi_app)

# Initialize the DynamoDB handler
dbname = os.environ.get("DYNAMODB_TABLE_NAME")
db = DynamoDBHandler(os.environ.get("DYNAMODB_TABLE_NAME"))

def mention_user(user_id):
    return f"<@{user_id}>"

@app.route("/", methods=["POST"])
async def interactions():
    print(f"👉 Request: {request.json}")
    raw_request = request.json
    return interact(raw_request)


@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interact(raw_request):
    if raw_request["type"] == 1:  # PING
        return jsonify({"type": 1})  # PONG
    
    data = raw_request["data"]
    command_name = data["name"]
    user_id = raw_request["member"]["user"]["id"]

    match command_name:
        case "hello":
            message_content = "Hello there!!!!!"
        case "echo":
            original_message = data["options"][0]["value"]
            message_content = f"Echoing: {original_message}"
        case "oops":
            victim = data["options"][0]["value"]
            cause_of_death = data["options"][1]["value"] if len(data["options"]) > 1 else "unknown"
            last_words = data["options"][2]["value"] if len(data["options"]) > 2 else None
            try:
                db.add_kill(user_id, victim, cause_of_death)
                message_content = f"Oops! {mention_user(user_id)} killed {mention_user(victim)} by {cause_of_death}."
                if last_words:
                    message_content += f" Their last words were: '{last_words}'"
            except Exception as e:
                message_content = f"Error recording oops: {str(e)}"
        case "ettu":
            betrayer = data["options"][0]["value"]
            murder_weapon = data["options"][1]["value"] if len(data["options"]) > 1 else "unknown"
            last_words = data["options"][2]["value"] if len(data["options"]) > 2 else None
            try:
                db.add_kill(betrayer, user_id, murder_weapon)
                if murder_weapon != "unknown":
                    print(murder_weapon)
                    message_content = f"Et tu, {mention_user(betrayer)}? Then fall, {mention_user(user_id)} (by {murder_weapon})!"
                else:
                    message_content = f"Et tu, {mention_user(betrayer)}? Then fall, {mention_user(user_id)}!"
                if last_words:
                    message_content += f" {mention_user(user_id)}'s last words: '{last_words}'"
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
                kill_count_difference = user_kills - compare_kills #db.compare_kill_counts(user_id, compare_user)

                message_content = f"{mention_user(user_id)} has {user_kills} kills. {mention_user(compare_user)} has {compare_kills} kills.\n"

                lead_descriptors = {
                    0: "no grudge",
                    1: "a budding grudge",
                    2: "a double grudge ",
                    3: "a triple grudge",
                    4: "a QUADRUPLE grudge",
                    5: "a PENTAGRUDGE",
                    6: "a MONSTER GRUDGE",
                    10: "an OMEGA SUPER GRUDGE",
                    15: "an ETERNAL GRUDGE",
                    20: "a DOUBLE-ETERNAL INTERSOLAR GIGAGRUDGE",
                    25: "a grudge whose magnitude exceeds conceptualization",
                    30: "a grudge so intense and painful that it is more like love",
                }
                
                for threshold, descriptor in sorted(lead_descriptors.items(), reverse=True):
                    if abs(kill_count_difference) >= threshold:
                        if kill_count_difference > 0:            
                            message_content += f"{mention_user(user_id)} has {descriptor} against {mention_user(compare_user)} (+{kill_count_difference})."
                        elif kill_count_difference < 0:
                            message_content += f"{mention_user(compare_user)} has {descriptor} against {mention_user(user_id)} (+{abs(kill_count_difference)})."
                        break
                else:
                    message_content += "Both users are tied in their kill counts. No grudge detected. "
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

print("hi")
if __name__ == "__main__":
    app.run(debug=True)
