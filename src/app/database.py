import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from datetime import datetime

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

    def add_kill(self, user_id, target_user_id, cause_of_death):
        try:
            # Get the current UTC time and format it as ISO 8601 string
            timestamp = datetime.utcnow().isoformat()
            
            # Update the item in the DynamoDB table
            response = self.table.update_item(
                # Specify the item to update using its composite primary key
                Key={
                    'UserId': user_id,
                    'TargetUserId': target_user_id
                },
                # Define the update operation: append to KillRecords list
                UpdateExpression="SET KillRecords = list_append(if_not_exists(KillRecords, :empty_list), :new_kill)",
                # Define the values used in the UpdateExpression
                ExpressionAttributeValues={
                    ':empty_list': [],  # Used if KillRecords doesn't exist yet
                    ':new_kill': [{     # The new kill record to append
                        'Timestamp': timestamp,
                        'CauseOfDeath': cause_of_death
                    }]
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

    def get_kill_count(self, user_id):
        """
        Retrieves the total number of kills for a specific user across all their targets.
        
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
                kill_count += len(kill_records)

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