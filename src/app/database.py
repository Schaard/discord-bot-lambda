import boto3
from boto3.dynamodb.conditions import Key, Attr
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import logging
import os
import requests
import discord

class DynamoDBHandler:
    def __init__(self, table_name):
        # Initialize the DynamoDB resource
        self.dynamodb = boto3.resource('dynamodb')
        # Get a reference to the specific table we'll be using
        self.table = self.dynamodb.Table(table_name)

    #Updating DB
    def add_kill(self, submitter_id, user_id, target_user_id, cause_of_death, server_id, game_id, channel_id, timestamp, unforgivable=False, forgiven=False):
        try:
            kill_record = {
            'SubmitterId': submitter_id,
            'CauseOfDeath': cause_of_death,
            'Timestamp': timestamp,
            'ServerId': server_id,
            'GameId': game_id,
            'ChannelId': channel_id,
            'Unforgivable': unforgivable,
            'Forgiven': forgiven
            }

            # Update the item in the DynamoDB table
            response = self.table.update_item(
                # Specify the item to update using its composite primary key
                Key={
                    'UserId': user_id,
                    'TargetUserId': target_user_id
                },
                # Define the update operation: append to KillRecords list
                UpdateExpression="SET KillRecords = list_append(if_not_exists(KillRecords, :empty_list), :new_kill), ServerId = :server_id",
                # Define the values used in the UpdateExpression
                ExpressionAttributeValues={
                    ':empty_list': [],  # Used if KillRecords doesn't exist yet
                    ':new_kill': [kill_record],
                    ':server_id': server_id
                },
                # Specify that we want the updated values returned
                ReturnValues="UPDATED_NEW"
            )
            # Return the response from DynamoDB
            return response
        except ClientError as e:
            # If an error occurs, print it and re-raise the exception
            print(f"Error adding kill: {e.response['Error']['Message']}")
            raise
    def forgive_kill(self, user_id, victim, timestamp):
        try:
            # Retrieve the kills for the given user and victim
            kill_records = self.get_kills(user_id, victim)
            
            # Check if any kills exist
            if not kill_records:
                return f"No kill records found for {user_id} on {victim}"
            
            # Find the kill record with the matching timestamp
            for kill in kill_records:
                if kill['Timestamp'] == timestamp:
                    # Mark the kill as forgiven
                    kill['Forgiven'] = True
                    break
            else:
                # If no matching timestamp was found, return an error
                return f"No kill record found with the timestamp {timestamp}"

            # Update the kill records in DynamoDB
            response = self.table.update_item(
                Key={
                    'UserId': user_id,
                    'TargetUserId': victim
                },
                UpdateExpression="SET KillRecords = :updated_records",
                ExpressionAttributeValues={
                    ':updated_records': kill_records
                },
                ReturnValues="UPDATED_NEW"
            )

            return response
            
        except ClientError as e:
            print(f"Error forgiving kill: {e.response['Error']['Message']}")
            raise  

    #Get Kill Data
    def get_kills(self, user_id, target_user_id, server_id = None, entitlement_active = False):
        try:
            # Retrieve a specific item from the DynamoDB table
            response = self.table.get_item(
                # Specify the item to retrieve using its composite primary key
                Key={
                    'UserId': user_id,
                    'TargetUserId': target_user_id
                }
            )

            # Return the KillRecords list from the item, or an empty list if not found
            kill_records =  response.get('Item', {}).get('KillRecords', [])

            # Filter records based on ServerId if server_id is not None
            if server_id is not None:
                server_filtered_records = [kill for kill in kill_records if kill.get('ServerId') == server_id]
            else:
                server_filtered_records = kill_records  # No server filtering if server_id is None

            # If entitlement is active, return all server-filtered records
            if entitlement_active:
                return server_filtered_records

            # If entitlement is not active, filter for current month
            current_date = datetime.now(timezone.utc)
            time_filtered_records = []
            
            for kill in server_filtered_records:
                kill_date = datetime.fromisoformat(kill['Timestamp'].replace('Z', '+00:00'))
                if kill_date.year == current_date.year and kill_date.month == current_date.month:
                    time_filtered_records.append(kill)
            
            return time_filtered_records            

        except ClientError as e:
            # If an error occurs, print it and re-raise the exception
            print(f"Error retrieving kills: {e.response['Error']['Message']}")
            raise              
    def get_unforgivens_on_user(self, user_id, victim, server_id = None, entitlement_active = False):
        try:
            # Retrieve the kills for the given user and victim
            kill_records = self.get_kills(user_id, victim, server_id, entitlement_active)
            #print(f"Total kills for {user_id} on {victim}: {kill_records}")
            # Filter out the unforgiven kills
            unforgiven_kills = [kill for kill in kill_records if not kill['Forgiven']]
            #print(f"Unforgiven kills for {user_id} on {victim} : {unforgiven_kills}")
            return unforgiven_kills
        except ClientError as e:
            print(f"Error retrieving unforgiven kills: {e.response['Error']['Message']}")
            raise
    def get_unforgivencount_on_user(self, user_id, victim, server_id = None, entitlement_active = False):
        try:
            # Retrieve the kills for the given user and victim
            unforgiven_kill_number = len(self.get_unforgivens_on_user(user_id, victim, server_id, entitlement_active))
            return unforgiven_kill_number
        except ClientError as e:
            print(f"Error counting unforgiven kills: {e.response['Error']['Message']}")
            raise

    #String gen 
    def get_grudge_string(self, user_id, user_kills, compare_user, compare_kills, no_article = False):
        #if the user_id and the compare_user_id are the same, just take the total kills instead of comparing
        logging.info(f"get_grudge_string: {user_id} {user_kills} {compare_user} {compare_kills}")
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
            7: "⚡ an OMEGA SUPER GRUDGE ⚡",
            8: "🧬 a GENETICALLY ENGINEERED SUPER GRUDGE 🧬",
            9: "🚨 a GRUDGE-LEVEL RED (emergency protocols activated) 🚨",
            10: "📜 an ANCIENT GRUDGE, foretold in portents unseen, inscribed in the stars themselves 📜",
            11: "💔 a grudge so intense and painful that it is more like love 💔",
            12: "🧨 a CATASTROPHIC grudge 🧨",
            13: "🌋 a grudge of apocalyptic proportions 🌋",
            14: "🦖 a PREHISTORIC grudge that refuses to go extinct 🦖",
            15: "🏰 GRUDGEHOLDE: an imposing stronghold built of pure grudge 🏰",
            16: "👑 a ROYAL grudge demanding fealty from all lesser grudges 👑",
            17: "🕵️‍♂️ a grudge currently under investigation for prohibited grudge levels 🕵️‍♂️",
            18: "💫 a grudge whose magnitude exceeds conceptualization 💫",
            19: "⏳ an ETERNAL GRUDGE ⏳",
            20: "🚀 a DOUBLE-ETERNAL INTERSOLAR GIGAGRUDGE 🚀",
            21: "🔻 a TRIPLE-ETERNAL (???) INTERSOLAR GIGAGRUDGE 🔻",
            22: "🕳️ an ALL-CONSUMING black hole of grudge which draws other, smaller grudges to itself, incorporating them into its power for a purpose unfathomable by higher minds than the primitive organic mass of logical shambling that is the human brain 🕳️",
            23: "🌌 a COSMIC GRUDGE spanning the entire grudgepast, grudgepresent, and grudgefuture 🌌",
            24: "👾 a GOD-TIER allgrudge transcending grudgespace and grudgetime 👾",
            69: "nice (grudge)",
            420: "blazing grudge"
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
        #grudge_descriptor += f" ({abs(kill_count_difference)})"
        # Optionally remove the article
        #if no_article:
        #    grudge_descriptor = remove_article(grudge_descriptor)

        return grudge_descriptor
    def get_name_fromid(self, user_id):
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
            return "Unknown User"  

    #Reports
    def get_top_killers(self, server_id, entitlement_active):
        try:
            limit = 11 if entitlement_active else 4
            
            response = self.table.query(
                IndexName='ServerId-index',  # Using the existing GSI
                KeyConditionExpression=Key('ServerId').eq(server_id)
            )

            # Get current date for filtering
            current_date = datetime.now(timezone.utc)

            # Count kills for each user
            kill_counts = {}
            for item in response['Items']:
                killer = item['UserId']
                # Filter out forgiven kills
                unforgiven_kills = []                
                for kill in item.get('KillRecords', []): 
                    if not kill.get('Forgiven', False):
                        if entitlement_active:
                            unforgiven_kills.append(kill)
                        else:
                            # Parse the timestamp and check if it's in the current month
                            kill_date = datetime.fromisoformat(kill['Timestamp'].replace('Z', '+00:00'))
                            if kill_date.year == current_date.year and kill_date.month == current_date.month:
                                unforgiven_kills.append(kill)
                kills = len(unforgiven_kills)                
                #kills = len(item.get('KillRecords', []))
                if kills > 0:
                    if killer in kill_counts:
                        kill_counts[killer] += kills
                    else:
                        kill_counts[killer] = kills
            
            # Sort users by kill count and get top 'limit' killers
            top_killers = sorted(kill_counts.items(), key=lambda x: x[1], reverse=True)
            
            return top_killers[:limit]
        except ClientError as e:
            print(f"Error getting top killers: {e.response['Error']['Message']}")
            raise   
    def get_wrapped_report(self, server_id, start_date, end_date):
        """
        Generate a Spotify Wrapped-style report for a server, summarizing monthly friendly-fire stats.
        
        :param server_id: The ID of the server for which the report is generated.
        :param start_date: The starting date of the period to be analyzed.
        :param end_date: The ending date of the period to be analyzed.
        :return: A formatted string summarizing the stats.
        """
        logging.info(f"Querying records from {start_date.isoformat()} to {end_date.isoformat()} for server: {server_id}")

        try:
         
            # Query the GSI
            response = self.table.query(
            IndexName='ServerId-index',
            KeyConditionExpression=Key('ServerId').eq(server_id),
                FilterExpression=Attr('KillRecords').exists(),
            ProjectionExpression='UserId, TargetUserId, KillRecords',

            )

            logging.info(f"DynamoDB Query Response: {response}")
            
            processed_items = []
            for item in response['Items']:
                for kill_record in item.get('KillRecords', []):
                    timestamp = kill_record.get('Timestamp')
                    forgiveness = kill_record.get('Forgiven', False)
                    if timestamp:
                        kill_date = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
                        if start_date <= kill_date <= end_date:
                            processed_item = {
                                'Timestamp': timestamp,
                                'UserId': item['UserId'],
                                'TargetUserId': item['TargetUserId'],
                                'ChannelId': kill_record.get('ChannelId', 'Unknown'),
                                'Forgiven': forgiveness,
                                'CauseOfDeath': item.get('CauseOfDeath', None),
                                'LastWords': item.get('LastWords', None)
                           }
                            processed_items.append(processed_item)

            # Now processed_items contains the data in the desired format
            #logging.info(f"Processed Items: {processed_items}")


            if not response['Items']:
                logging.warning(f"No records found for server {server_id} between {start_date} and {end_date}")
                return "No kills recorded this month. Your team must be getting along well!"
            
            # Process the query results
            #deserializer = TypeDeserializer()
            kill_stats = self._process_kill_records(processed_items, server_id, start_date, end_date)

            # Build and return the Wrapped-style summary message
            report = self._build_report(kill_stats, processed_items, start_date, end_date)
            return report
        
        except Exception as e:
            logging.error(f"Error generating report: {e}")
            return f"Error generating report: {e}"
    def _process_kill_records(self, items, server_id, start_date, end_date):
        """
        Process kill records and generate statistics.
        
        :param items: List of items from DynamoDB response.
        :param server_id: The ID of the server.
        :param start_date: The starting date of the period to be analyzed.
        :param end_date: The ending date of the period to be analyzed.
        :return: A dictionary containing processed statistics.
        """
        stats = {
            'kills_by_user': defaultdict(int),
            'kills_by_victim': defaultdict(int),
            'forgiveness_count': defaultdict(int),
            'forgiveness_received': defaultdict(int),
            'unforgiven_kills': defaultdict(lambda: defaultdict(int)),
            'kills_by_channel': defaultdict(int),
            'multi_kills': defaultdict(lambda: defaultdict(list)),
            'first_incident': None,
            'last_incident': None  
        }

        for record in items:
            logging.info(f"Processing kill record: {record}")
                
            killer_id = record['UserId']
            victim_id = record['TargetUserId']
            forgiven = record.get('Forgiven', False)
            timestamp = datetime.fromisoformat(record['Timestamp'])            
            channel_id = record['ChannelId']
            
            # Track first and last incidents
            if stats['first_incident'] is None or timestamp < stats['first_incident']['timestamp']:
                stats['first_incident'] = {
                    'timestamp': timestamp,
                    'killer': killer_id,
                    'victim': victim_id,
                    'cause_of_death': record.get('CauseOfDeath'),  # Use .get() to safely handle missing keys
                    'last_words': record.get('LastWords')
                }
            if stats['last_incident'] is None or timestamp > stats['last_incident']['timestamp']:
                stats['last_incident'] = {
                    'timestamp': timestamp,
                    'killer': killer_id,
                    'victim': victim_id,
                    'cause_of_death': record.get('CauseOfDeath'),  # Use .get() to safely handle missing keys
                    'last_words': record.get('LastWords')
                }

            # Track kill counts
            stats['kills_by_user'][killer_id] += 1
            stats['kills_by_victim'][victim_id] += 1
            stats['kills_by_channel'][channel_id] += 1  

            # Track multi-kills
            if victim_id in stats['multi_kills'][killer_id]:
                last_kill_time = stats['multi_kills'][killer_id][victim_id][-1]
                if timestamp - last_kill_time <= timedelta(hours=12):
                    stats['multi_kills'][killer_id][victim_id].append(timestamp)
                else:
                    stats['multi_kills'][killer_id][victim_id] = [timestamp]
            else:
                stats['multi_kills'][killer_id][victim_id] = [timestamp]


            # Track forgiveness
            if forgiven:
                stats['forgiveness_count'][victim_id] += 1  # The victim is doing the forgiving
                stats['forgiveness_received'][killer_id] += 1 # The killer is being forgiven
            else:
                # Track unforgiven kills for grudge detection
                stats['unforgiven_kills'][killer_id][victim_id] += 1

        return stats
    def get_kills_bidirectional(self, user_id, target_user_id):
        try:
            response1 = self.table.query(
                KeyConditionExpression=Key('UserId').eq(user_id) & Key('TargetUserId').eq(target_user_id)
            )
            response2 = self.table.query(
                KeyConditionExpression=Key('UserId').eq(target_user_id) & Key('TargetUserId').eq(user_id)
            )
            return response1.get('Items', []) + response2.get('Items', [])

        except ClientError as e:
            print(f"Error retrieving kills: {e.response['Error']['Message']}")
            raise
    def _build_report(self, kill_stats, processed_items, start_date, end_date):
        """ Helper method to build the report string from the data """
        month_year = start_date.strftime("%B %Y")
        report = f"**🌟 Friendly-Fire Wrapped: Your Server's Month in Grudges ({month_year}) 🌟**\n"

        # Calculate total kills
        total_kills = sum(kill_stats['kills_by_user'].values())
        report += f"🎯 In Case You Missed It: Your Server's Stats Are In! 🎯 "
        report += f"\n Collectively, you recorded a whopping **{total_kills} friendly-fire incidents** this month.\n"

        # Add first and last incident information
        if kill_stats['first_incident']:
            first = kill_stats['first_incident']
            report += f"\n🔥 **(Friendly) Firestarter Award: First Kill of the Month** 🔥 "
            report += f"On {first['timestamp'].strftime('%B %d')} at {first['timestamp'].strftime('%I:%M %p')}, "
            report += f"<@{first['killer']}> kicked off the month by taking out <@{first['victim']}>!"
            
            if first.get('cause_of_death'):
                report += f" The cause? {first['cause_of_death']}."
            
            if first.get('last_words'):
                report += f" This first last words were: \"{first['last_words']}\""

        # Add channel insights
        if kill_stats['kills_by_channel']:
            top_channel = max(kill_stats['kills_by_channel'], key=kill_stats['kills_by_channel'].get)
            top_channel_kills = kill_stats['kills_by_channel'][top_channel]
            report += f"\n\n💥 **The 'Danger Zone' Award** 💥 The channel <#{top_channel}> is our server's friendly-fire hotspot with {top_channel_kills} incidents!\n"
        else:
            report += "\n🏞️ All channels seem equally peaceful (or chaotic). No danger zones detected! 🏞️\n"

        if total_kills == 0:
            report += f"☮️ No one's been racking up kills...yet! ☮️\n"
        else:
            # Top Killer
            top_killer = max(kill_stats['kills_by_user'], key=kill_stats['kills_by_user'].get)
            report += f"🏆 **The 'Oops, My Bad' Award** 🏆 goes to <@{top_killer}> with {kill_stats['kills_by_user'][top_killer]} friendly-fire incidents!\n"

            # Most Forgiving
            most_forgiving = max(kill_stats['forgiveness_count'], key=kill_stats['forgiveness_count'].get, default=None)
            if most_forgiving:
                report += f"😇 **The 'Turn the Other Cheek' Award** 😇 is earned by <@{most_forgiving}> for forgiving {kill_stats['forgiveness_count'][most_forgiving]} times!\n"

            # Most Forgiven (new code)
            most_forgiven = max(kill_stats['forgiveness_received'], key=kill_stats['forgiveness_received'].get, default=None)
            if most_forgiven:
                report += f"🧲 **The 'Forgiveness Magnet' Award** 🧲 goes to <@{most_forgiven}> for being forgiven {kill_stats['forgiveness_received'][most_forgiven]} times!\n"
            else:
                report += "���️ No one's been forgiven...yet! ���️\n"
            # Biggest Victim
            biggest_victim = max(kill_stats['kills_by_victim'], key=kill_stats['kills_by_victim'].get)
            report += f"☠️ **The 'Human Shield' Award** ☠️ is reluctantly accepted by <@{biggest_victim}>, killed {kill_stats['kills_by_victim'][biggest_victim]} times!\n"

            # Biggest Grudge
            biggest_grudge = max(
                ((killer, victim, count) 
                for killer, victims in kill_stats['unforgiven_kills'].items() 
                for victim, count in victims.items()),
                key=lambda x: x[2],
                default=(None, None, 0)
            )
            if biggest_grudge[0]:
                report += f"🧊 **The 'Ice in Their Veins' Award** 🧊 goes to <@{biggest_grudge[1]}> for not forgiving <@{biggest_grudge[0]}> {biggest_grudge[2]} times!\n"

            # Multi-kill insights
            multi_kill_insights = self.generate_multi_kill_insights(processed_items)
            if multi_kill_insights:
                report += "🤯 **The Team Multi-Kill Award** 🤯 "
                for insight in multi_kill_insights:
                    report += insight + "\n"

            if kill_stats['last_incident']:
                last = kill_stats['last_incident']
                report += f"\n🏁 **The Month's Final Betrayal** 🏁 "
                report += f"The final friendly-fire of {month_year} occurred on {last['timestamp'].strftime('%B %d')} at {last['timestamp'].strftime('%I:%M %p')}, "
                report += f"when <@{last['killer']}> caught <@{last['victim']}> off-guard."
                
                if last.get('cause_of_death'):
                    report += f" The finishing blow? {last['cause_of_death']}."
                
                if last.get('last_words'):
                    report += f" We'll always remember their final words: \"{last['last_words']}\""
                
            report += "\n"

        return report
    def generate_multi_kill_insights(self, kills):
        #logging.info(f"Starting to generate multi-kill insights. Total kills to process: {len(kills)}")
        multi_kill_insights = []
        
        # Group kills by killer and victim
        kill_groups = {}
        for kill in kills:
            key = (kill['UserId'], kill['TargetUserId'])
            if key not in kill_groups:
                kill_groups[key] = []
            kill_groups[key].append(kill)
        
        #logging.info(f"Grouped kills into {len(kill_groups)} killer-victim pairs")

        for (killer, victim), group in kill_groups.items():
            logging.debug(f"Processing group: Killer {killer}, Victim {victim}, Kills: {len(group)}")
            if len(group) >= 3:
                # Sort kills by timestamp
                sorted_kills = sorted(group, key=lambda k: datetime.fromisoformat(k['Timestamp']))
                
                # Calculate the total time window
                first_kill = datetime.fromisoformat(sorted_kills[0]['Timestamp'])
                last_kill = datetime.fromisoformat(sorted_kills[-1]['Timestamp'])
                total_time_diff = last_kill - first_kill
                
                #logging.debug(f"Time window for group: {last_kill} - {first_kill} = {total_time_diff}")

                if total_time_diff <= timedelta(hours=12):
                    # Format the time difference
                    if total_time_diff.total_seconds() < 60:
                        time_str = f"{int(total_time_diff.total_seconds())} seconds"
                    elif total_time_diff.total_seconds() < 3600:
                        time_str = f"{int(total_time_diff.total_seconds() / 60)} minutes"
                    else:
                        time_str = f"{total_time_diff.total_seconds() / 3600:.1f} hours"
                    
                    # Generate the insight
                    kill_count = len(group)
                    kill_type = {3: "Triple", 4: "Quadruple", 5: "Quintuple"}.get(kill_count, "Multi")
                    insight = f"{kill_type} kill! <@{killer}> went on a rampage against <@{victim}>, scoring {kill_count} kills in {time_str}! Impressive... or concerning? 🤔"
                    multi_kill_insights.append(insight)
                    #logging.info(f"Generated multi-kill insight: {insight}")
                else:
                    logging.debug(f"Group not qualified for multi-kill (time window > 12 hours)")
            else:
                logging.debug(f"Group not qualified for multi-kill (less than 3 kills)")

        logging.info(f"Finished generating multi-kill insights. Total insights: {len(multi_kill_insights)}")
        return multi_kill_insights    
    def generate_grudge_report(self, user1, user2, limit=8, page=0, server_id = None, entitlement_active = False):
        #IDEA: RESTRICT SECOND ARGUMENT TO PREMIUM 
        try:
            kill_data = self.get_kills_bidirectional(user1, user2)
            grudge_count = 0
            incidents = []
            
            # Process kills from user1 to user2
            for kill in kill_data[0].get('KillRecords', []):
                forgiven_value = kill.get('Forgiven', False)
                server_value = kill.get('ServerId', 'Unknown')
                if server_id is None or server_value is server_id:
                    incidents.append({
                        'UserId': user1,
                        'TargetUserId': user2,
                        'Timestamp': kill.get('Timestamp'),
                        'CauseOfDeath': kill.get('CauseOfDeath', 'Unknown'),
                        'LastWords': kill.get('LastWords', 'None'),
                        'Forgiven': forgiven_value
                    })
            # Process kills from user2 to user1
            for kill in kill_data[1].get('KillRecords', []):
                forgiven_value = kill.get('Forgiven', False)
                server_value = kill.get('ServerId', 'Unknown')
                if server_id is None or server_value is server_id:
                    incidents.append({
                        'UserId': user2,
                        'TargetUserId': user1,
                        'Timestamp': kill.get('Timestamp'),
                        'CauseOfDeath': kill.get('CauseOfDeath', 'Unknown'),
                        'LastWords': kill.get('LastWords', ''),
                        'Forgiven': forgiven_value
                    })

            #logging.info(f"Processed incidents: {incidents}")

            # Sort incidents by timestamp for grudge calc
            incidents.sort(key=lambda x: x.get('Timestamp', ''), reverse=False)
            left_unforgiven_count = 0
            right_unforgiven_count = 0
            grudge_count = 0
            for incident in incidents:
                forgiven_val = incident['Forgiven']
                if not forgiven_val:
                    killer_is_left = incident['UserId'] == user1
                    if killer_is_left:
                        grudge_count -= 1
                        left_unforgiven_count += 1
                    else:
                        grudge_count += 1
                        right_unforgiven_count += 1
                incident['GrudgeCount'] = grudge_count
                incident['LeftUnforgivenCount'] = left_unforgiven_count
                incident['RightUnforgivenCount'] = right_unforgiven_count
            
            # Sort incidents by timestamp
            incidents.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)            
            
            # Apply pagination
            start_index = page * limit
            end_index = start_index + limit
            paginated_incidents = incidents[start_index:end_index]
            
            # Check if there are more incidents
            has_more = len(incidents) > end_index
            
            if not incidents:
                return f"No incidents found between these two users."
            
            # Use get_named_fromid to get usernames
            #print(f" Non-paginated incidents: {incidents}")
            #print(f" Paginated incidents: {paginated_incidents}")
            left_user_id = incidents[0]['UserId']
            right_user_id = incidents[0]['TargetUserId']
            # Get usernames
            left_name = self.get_name_fromid(left_user_id)
            right_name = self.get_name_fromid(right_user_id)
            
            grudgeholder_name = left_name if grudge_count > 0 else right_name
            left_unforgivencount_on_right = self.get_unforgivencount_on_user(left_user_id, right_user_id, server_id, entitlement_active)
            right_unforgivencount_on_left = self.get_unforgivencount_on_user(right_user_id, left_user_id, server_id, entitlement_active)
            begrudged_name = right_name if grudgeholder_name == left_name else left_name
            logging.info(f"grudgeholder_name: {grudgeholder_name}, begrudged_name: {begrudged_name}, left_unforgivencount_on_right: {left_unforgivencount_on_right}, right_unforgivencount_on_left: {right_unforgivencount_on_left}")
            grudge_desc_string = self.get_grudge_string(left_user_id, left_unforgivencount_on_right, right_user_id, right_unforgivencount_on_left)
            current_grudge_string = f"A {abs(grudge_count)} point difference in unforgiven kills gives {grudgeholder_name}\n {grudge_desc_string} against {begrudged_name}."
            # Create the embed
            embed = discord.Embed(
                title=f"📜 Grudges between {left_name} and {right_name} 📜",
                description=f"(Showing incidents {start_index + 1}-{min(end_index, len(incidents))} out of {len(incidents)})",
                color=discord.Color.blue().value,
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/553164743720960010/1296332288484708383/icon64.png?ex=6711e706&is=67109586&hm=90dd6486c2ba6e755b6cdca80182867367bfe95cbb627bba7b03472d3ce3a01d&")
            
            footer_text = "Generated by GrudgeKeeper Free" if not entitlement_active else "Generated by GrudgeKeeper Premium"
            embed.set_footer(
            text=f"{footer_text}",
            icon_url="https://cdn.discordapp.com/attachments/553164743720960010/1296352648001359882/icon32.png?ex=6711f9fc&is=6710a87c&hm=1d1dfe458616c494f06d4018f7bad0e7dd6a9590f742d003742821183125509e&"
            )

            # Add header row
            embed.add_field(name="Grudge Balance:", value=f"{current_grudge_string}", inline=False)
            #embed.add_field(name="Killer → Victim", value="\u200b", inline=True)
            #embed.add_field(name="Grudge Count", value="\u200b", inline=True)
            previous_grudge_count = 0
            # Add each incident as a field in the embed
            for incident in paginated_incidents:
                timestamp = datetime.fromisoformat(incident['Timestamp']).strftime('%-m/%d/%-y, %-I:%M %p')

                killer_name_is_left = incident['UserId'] == user1

                killer_name = left_name if killer_name_is_left else right_name
                victim_name = right_name if killer_name_is_left else left_name

                cause_of_death = incident.get('CauseOfDeath', 'Unknown')
                last_words = incident.get('LastWords', 'None')
                forgiven = "Yes" if incident.get('Forgiven', False) else "No"
                grudge_count = incident.get('GrudgeCount', 'None')
                left_unforgivens = incident.get('LeftUnforgivenCount', 'None')
                right_unforgivens = incident.get('RightUnforgivenCount', 'None')
                
                kill_directional_arrow = "🔪" if killer_name_is_left else "🗡️"
                main_message_embed_value = f"{left_name} {kill_directional_arrow} {right_name}\n"
                embed.add_field(name=f"{timestamp}", value=main_message_embed_value, inline=True)
                
                # Generate the dynamic grudge change string
                grudge_change_string = f"{grudgeholder_name} leads by {abs(grudge_count)}" if abs(grudge_count) != 0 else ""

                grudgeholder_name = left_name if grudge_count > 0 else right_name
                if forgiven == "Yes": grudge_change_string = "No change (forgiven)"
                grudge_string = f"{grudge_change_string}" 
                embed.add_field(name=f"Grudges: {left_unforgivens} v {right_unforgivens}", value=f"{grudge_string}", inline=True)
                
                cod_and_lw_combostring = ""
                if cause_of_death and cause_of_death.lower() != "unknown":
                    cod_and_lw_combostring += f"Killed by {cause_of_death}.\n"
                if last_words and last_words != "None":
                    cod_and_lw_combostring += f"\n{last_words}"
                if cod_and_lw_combostring != "": embed.add_field(name="Notes", value=f"{cod_and_lw_combostring.strip()}", inline=True)
                else: embed.add_field(name="\u200b", value=f"\u200b", inline=True)

            logging.info(f"Generated grudge report embed and has_more: {has_more}")
            dicted_embed = embed.to_dict()
            logging.info(f"Dicted embed: {dicted_embed}")
            return dicted_embed, has_more
        except Exception as e:
            logging.error(f"Error in generate_grudge_report: {str(e)}", exc_info=True)
            return f"An error occurred while generating the grudge report: {str(e)}"