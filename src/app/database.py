import boto3
from boto3.dynamodb.conditions import Key, Attr
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import logging

class DynamoDBHandler:
    def __init__(self, table_name):
        # Initialize the DynamoDB resource
        self.dynamodb = boto3.resource('dynamodb')
        # Get a reference to the specific table we'll be using
        self.table = self.dynamodb.Table(table_name)

    def save_data(self, user_id, data):
        try:
            response = self.table.put_item(
                Item={
                    'Killer': user_id,
                    'data': data
                }
            )
            print(f"Save response: {response}")  # Add this for debugging
            return response
        except ClientError as e:
            error_message = f"Error saving data: {e.response['Error']['Message']}"
            print(error_message)
            raise Exception(error_message)  # Raise the exception to be caught in the main function

    def get_data(self, user_id):
        try:
            response = self.table.get_item(
                Key={
                    'Killer': user_id
                }
            )
            item = response.get('Item')
            print(f"Retrieved item: {item}")  # Add this for debugging
            return item
        except ClientError as e:
            error_message = f"Error retrieving data: {e.response['Error']['Message']}"
            print(error_message)
            raise Exception(error_message)
    
    def __init__(self, table_name):
        # Initialize the DynamoDB resource
        self.dynamodb = boto3.resource('dynamodb')
        # Get a reference to the specific table we'll be using
        self.table = self.dynamodb.Table(table_name)

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
    def remove_latest_command(self, user_id):
        try:
            # Query all items where this user is either the killer or the victim
            response = self.table.query(
                IndexName='UserIdIndex',  # You'll need to create this GSI
                KeyConditionExpression=Key('UserId').eq(user_id)
            )

            items = response['Items']
            if not items:
                return None

            # Find the item with the most recent kill where this user is the killer
            latest_item = max(items, key=lambda x: max(kill['Timestamp'] for kill in x.get('KillRecords', [])) if x.get('KillRecords') else '')

            if not latest_item.get('KillRecords'):
                return None

            # Find and remove the most recent kill record
            latest_kill = max(latest_item['KillRecords'], key=lambda x: x['Timestamp'])
            latest_item['KillRecords'].remove(latest_kill)

            # Update the item in the database
            self.table.put_item(Item=latest_item)

            return {
                'KillerUserId': latest_item['UserId'],
                'TargetUserId': latest_item['TargetUserId'],
                'CauseOfDeath': latest_kill['CauseOfDeath'],
                'Timestamp': latest_kill['Timestamp']
            }
        except ClientError as e:
            print(f"Error removing latest command: {e.response['Error']['Message']}")
            raise
    def get_kills(self, user_id, target_user_id):
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
            return response.get('Item', {}).get('KillRecords', [])
        except ClientError as e:
            # If an error occurs, print it and re-raise the exception
            print(f"Error retrieving kills: {e.response['Error']['Message']}")
            raise
    
    def get_unforgivens_on_user(self, user_id, victim):
        try:
            # Retrieve the kills for the given user and victim
            kill_records = self.get_kills(user_id, victim)
            print(f"Total kills for {user_id} on {victim}: {kill_records}")
            # Filter out the unforgiven kills
            unforgiven_kills = [kill for kill in kill_records if not kill['Forgiven']]
            print(f"Unforgiven kills for {user_id} on {victim} : {unforgiven_kills}")
            return unforgiven_kills
        except ClientError as e:
            print(f"Error retrieving unforgiven kills: {e.response['Error']['Message']}")
            raise
    def get_unforgivencount_on_user(self, user_id, victim):
        try:
            # Retrieve the kills for the given user and victim
            unforgiven_kill_number = len(self.get_unforgivens_on_user(user_id, victim))
            return unforgiven_kill_number
        except ClientError as e:
            print(f"Error counting unforgiven kills: {e.response['Error']['Message']}")
            raise    
    def get_grudge(self, user_id, victim):
        try:
            # Count the number of unforgiven kills on the first person 
            caller_unforgiven_count = self.get_unforgivencount_on_user(user_id, victim)
            #print(f"Caller unforgiven count: {caller_unforgiven_count}")
            # Count the number of unforgiven kills on the second person 
            victim_unforgiven_count = self.get_unforgivencount_on_user(victim, user_id)
            # Calculate the final tally
            #print(f"Victim unforgiven count: {victim_unforgiven_count}")
            final_tally = victim_unforgiven_count + caller_unforgiven_count
            logging.info(f"Killer Unforgivens: {caller_unforgiven_count}, Victim Unforgivens {victim_unforgiven_count}, final tally: {final_tally}")
            return final_tally
        except ClientError as e:
            print(f"Error comparing kills: {e.response['Error']['Message']}")
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
    def forgive_kill_by_index(self, user_id, target_user_id, index):
        try:
            # Get the current kill records
            kill_records = self.get_kills(user_id, target_user_id)
            
            # Check if the index is valid
            if index < 0 or index >= len(kill_records):
                raise ValueError("Invalid index for kill record")
            
            # Update the specified kill record
            kill_records[index]['Forgiven'] = True
            
            # Update the item in the DynamoDB table
            response = self.table.update_item(
                Key={
                    'UserId': user_id,
                    'TargetUserId': target_user_id
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
        except ValueError as e:
            print(f"Error forgiving kill: {str(e)}")
            raise

    def get_kill_count(self, user_id):
        """
        Retrieves the total number of kills for a specific user across all their targets that are marked as unforgiven.
        
        :param user_id: The ID of the user whose kill count is being retrieved
        :return: The total number of kills for the user
        """
        try:
            # Query the DynamoDB table for all items with the specified UserId
            response = self.table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('UserId').eq(user_id)
            )

            # Initialize the kill count
            kill_count = 0

            # Iterate through all items and sum up the lengths of KillRecords
            for item in response['Items']:
                kill_records = item.get('KillRecords', [])
                # Count only the kills that are not marked as forgiven
                unforgiven_kills = [kill for kill in kill_records if not kill.get('Forgiven', False)]
                kill_count += len(unforgiven_kills)

            return kill_count

        except ClientError as e:
            print(f"Error retrieving kill count: {e.response['Error']['Message']}")
            raise    
    def compare_kill_counts(self, user_id_1, user_id_2):
        """
        Compares the kill counts of two users and returns the difference.
        
        :param user_id_1: The ID of the first user
        :param user_id_2: The ID of the second user
        :return: The difference between the kill counts (user_id_2's kills on user_id_1 - user_id_1's kills on user_id_2)
        """
        try:
            # Get the kills of user_id_1 on user_id_2
            user_1_kills_on_2 = len(self.get_kills(user_id_1, user_id_2))
            
            # Get the kills of user_id_2 on user_id_1
            user_2_kills_on_1 = len(self.get_kills(user_id_2, user_id_1))
            
            # Calculate the difference
            kill_count_difference = user_2_kills_on_1 - user_1_kills_on_2
            
            return kill_count_difference
        
        except ClientError as e:
            print(f"Error comparing kill counts: {e.response['Error']['Message']}")
            raise    
    def get_top_killers(self, limit=10):
        try:
            # Scan the entire table
            response = self.table.scan()
            
            # Count kills for each user
            kill_counts = {}
            for item in response['Items']:
                killer = item['UserId']
                kills = len(item.get('KillRecords', []))
                if killer in kill_counts:
                    kill_counts[killer] += kills
                else:
                    kill_counts[killer] = kills
            
            # Sort users by kill count and get top 'limit' killers
            top_killers = sorted(kill_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            
            return top_killers
        except ClientError as e:
            print(f"Error getting top killers: {e.response['Error']['Message']}")
            raise
    def get_all_kills_for_user(self, user_id):
        try:
            # Query the DynamoDB table for all items with the specified UserId
            response = self.table.query(
                # Use a Key condition to filter items by UserId
                KeyConditionExpression=boto3.dynamodb.conditions.Key('UserId').eq(user_id)
            )
            # Return all items found by the query
            return response['Items']
        except ClientError as e:
            # If an error occurs, print it and re-raise the exception
            print(f"Error retrieving all kills: {e.response['Error']['Message']}")
            raise

    def undo_last_incident(self, user_id):
        try:
            # Retrieve the user's data from the DynamoDB table
            response = self.table.get_item(
                Key={
                    'UserId': user_id
                }
            )
            user_data = response.get('Item', {})

            # Extract the friendly fire and betrayal lists from the user data
            friendly_fire = user_data.get('FriendlyFire', [])
            betrayals = user_data.get('Betrayals', [])

            # Get the most recent incident from each list (if they exist)
            last_ff = friendly_fire[-1] if friendly_fire else None
            last_betrayal = betrayals[-1] if betrayals else None

            # Determine which incident was more recent and prepare the update accordingly
            if last_ff and last_betrayal:
                # If both exist, compare timestamps to find the most recent
                if last_ff['Timestamp'] > last_betrayal['Timestamp']:
                    friendly_fire.pop()
                    update_expression = "SET FriendlyFire = :ff"
                    expression_values = {':ff': friendly_fire}
                else:
                    betrayals.pop()
                    update_expression = "SET Betrayals = :b"
                    expression_values = {':b': betrayals}
            elif last_ff:
                # If only friendly fire exists, remove the last friendly fire incident
                friendly_fire.pop()
                update_expression = "SET FriendlyFire = :ff"
                expression_values = {':ff': friendly_fire}
            elif last_betrayal:
                # If only betrayal exists, remove the last betrayal incident
                betrayals.pop()
                update_expression = "SET Betrayals = :b"
                expression_values = {':b': betrayals}
            else:
                # If no incidents exist, return a message
                return "No incidents to undo."

            # Update the item in the DynamoDB table
            self.table.update_item(
                Key={
                    'UserId': user_id
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ReturnValues="UPDATED_NEW"
            )
            return "Last incident undone successfully."
        except ClientError as e:
            # Handle any DynamoDB client errors
            print(f"Error undoing last incident: {e.response['Error']['Message']}")
            raise
        except IndexError:
            # Handle the case where we try to pop from an empty list
            return "No incidents to undo."
    
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
                    if timestamp:
                        kill_date = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
                        if start_date <= kill_date <= end_date:
                            processed_item = {
                                'Timestamp': timestamp,
                                'UserId': item['UserId'],
                                'TargetUserId': item['TargetUserId'],
                                'ChannelId': kill_record.get('ChannelId', 'Unknown')  # Add this line
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
            'unforgiven_kills': defaultdict(lambda: defaultdict(int)),
            'kills_by_channel': defaultdict(int),
            'multi_kills': defaultdict(lambda: defaultdict(list))  
        }

        for record in items:
            logging.info(f"Processing kill record: {record}")
                
            killer_id = record['UserId']
            victim_id = record['TargetUserId']
            forgiven = record.get('Forgiven', {}).get('BOOL', False)
            timestamp = datetime.fromisoformat(record['Timestamp'])            
            channel_id = record['ChannelId']
            
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
                stats['forgiveness_count'][killer_id] += 1
            else:
                # Track unforgiven kills for grudge detection
                stats['unforgiven_kills'][killer_id][victim_id] += 1

        return stats


    def _build_report(self, kill_stats, processed_items, start_date, end_date):
        """ Helper method to build the report string from the data """
        month_year = start_date.strftime("%B %Y")
        report = f"**🌟 Friendly-Fire Wrapped: Your Server's Epic Moments ({month_year}) 🌟**\n\n"

        # Calculate total kills
        total_kills = sum(kill_stats['kills_by_user'].values())

        report += f"🎯 **In Case You Missed It: Your Server's Stats Are In!**\n"
        report += f"Collectively, you all recorded a whopping **{total_kills} friendly-fire incidents** this month. That's a lot of accidental backstabs! 🔪\n\n"

        # Add channel insights
        if kill_stats['kills_by_channel']:
            top_channel = max(kill_stats['kills_by_channel'], key=kill_stats['kills_by_channel'].get)
            top_channel_kills = kill_stats['kills_by_channel'][top_channel]
            report += f"\n🔥 **Danger Zone!** 🔥 The channel <#{top_channel}> is our server's friendly-fire hotspot with {top_channel_kills} incidents! Maybe it's time for some team-building exercises there?\n"
        else:
            report += "\n🏞️ All channels seem equally peaceful (or chaotic). No danger zones detected!\n"

        if total_kills == 0:
            report += f"💥 No one's been racking up kills...yet!\n"
        else:
            # Top Killer
            top_killer = max(kill_stats['kills_by_user'], key=kill_stats['kills_by_user'].get)
            report += f"🏆 **The 'Oops, My Bad' Award** goes to <@{top_killer}> with {kill_stats['kills_by_user'][top_killer]} friendly-fire incidents!\n"

            # Most Forgiving
            most_forgiving = max(kill_stats['forgiveness_count'], key=kill_stats['forgiveness_count'].get, default=None)
            if most_forgiving:
                report += f"😇 **The 'Turn the Other Cheek' Award** is earned by <@{most_forgiving}> for forgiving {kill_stats['forgiveness_count'][most_forgiving]} times!\n"

            # Biggest Victim
            biggest_victim = max(kill_stats['kills_by_victim'], key=kill_stats['kills_by_victim'].get)
            report += f"🎯 **The 'Human Shield' Award** is reluctantly accepted by <@{biggest_victim}>, targeted {kill_stats['kills_by_victim'][biggest_victim]} times!\n"

            # Biggest Grudge
            biggest_grudge = max(
                ((killer, victim, count) 
                for killer, victims in kill_stats['unforgiven_kills'].items() 
                for victim, count in victims.items()),
                key=lambda x: x[2],
                default=(None, None, 0)
            )
            if biggest_grudge[0]:
                report += f"🧊 **The 'Ice in Their Veins' Award** goes to <@{biggest_grudge[1]}> for not forgiving <@{biggest_grudge[0]}> {biggest_grudge[2]} times!\n"

            # Multi-kill insights
            multi_kill_insights = self.generate_multi_kill_insights(processed_items)
            if multi_kill_insights:
                report += "\n**Multi-Kill Madness!**\n"
                for insight in multi_kill_insights:
                    report += insight + "\n"

        return report

    def generate_multi_kill_insights(self, kills):
        logging.info(f"Starting to generate multi-kill insights. Total kills to process: {len(kills)}")
        multi_kill_insights = []
        
        # Group kills by killer and victim
        kill_groups = {}
        for kill in kills:
            key = (kill['UserId'], kill['TargetUserId'])
            if key not in kill_groups:
                kill_groups[key] = []
            kill_groups[key].append(kill)
        
        logging.info(f"Grouped kills into {len(kill_groups)} killer-victim pairs")

        for (killer, victim), group in kill_groups.items():
            logging.debug(f"Processing group: Killer {killer}, Victim {victim}, Kills: {len(group)}")
            if len(group) >= 3:
                # Sort kills by timestamp
                sorted_kills = sorted(group, key=lambda k: datetime.fromisoformat(k['Timestamp']))
                
                # Calculate the total time window
                first_kill = datetime.fromisoformat(sorted_kills[0]['Timestamp'])
                last_kill = datetime.fromisoformat(sorted_kills[-1]['Timestamp'])
                total_time_diff = last_kill - first_kill
                
                logging.debug(f"Time window for group: {last_kill} - {first_kill} = {total_time_diff}")

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
                    insight = f"We have a {kill_type} Kill champion! <@{killer}> went on a rampage against <@{victim}>, scoring {kill_count} kills in {time_str}! Impressive... or concerning? 🤔"
                    multi_kill_insights.append(insight)
                    logging.info(f"Generated multi-kill insight: {insight}")
                else:
                    logging.debug(f"Group not qualified for multi-kill (time window > 12 hours)")
            else:
                logging.debug(f"Group not qualified for multi-kill (less than 3 kills)")

        logging.info(f"Finished generating multi-kill insights. Total insights: {len(multi_kill_insights)}")
        return multi_kill_insights