import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DynamoDBHandler:
    def __init__(self):
        # Initialize the DynamoDB resource
        self.dynamodb = boto3.resource('dynamodb')
        # Get the table name from environment variables
        self.table_name = os.getenv('DYNAMODB_TABLE_NAME')
        # Get a reference to the specific table we'll be using
        self.table = self.dynamodb.Table(self.table_name)
    
    def ensure_table_exists(self):
        try:
            self.table.load()
            print(f"Table {self.table_name} exists.")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"Table {self.table_name} does not exist.")
                return False
            else:
                raise

    def create_table(self):
        print(f"Creating table {self.table_name}...")
        table = self.dynamodb.create_table(
            TableName=self.table_name,
            KeySchema=[
                {
                    'AttributeName': 'UserId',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'TargetUserId',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'UserId',
                    'AttributeType': 'S'  # String
                },
                {
                    'AttributeName': 'TargetUserId',
                    'AttributeType': 'S'  # String
                },
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            },
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'UserIdIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'UserId',
                            'KeyType': 'HASH'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    },
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ]
        )
        table.wait_until_exists()
        print(f"Table {self.table_name} created successfully.")

    def delete_table(self):
        print(f"Deleting table {self.table_name}...")
        self.table.delete()
        self.table.wait_until_not_exists()
        print(f"Table {self.table_name} deleted successfully.")

    def restructure_table(self):
        if self.ensure_table_exists():
            self.delete_table()
        self.create_table()

    def add_gsi(self):
        print(f"Adding Global Secondary Index to table {self.table_name}...")
        try:
            self.table.update(
                AttributeDefinitions=[
                    {
                        'AttributeName': 'ServerId',
                        'AttributeType': 'S'
                    },
                    {
                        'AttributeName': 'Timestamp',
                        'AttributeType': 'S'
                    },
                ],
                GlobalSecondaryIndexUpdates=[
                    {
                        'Create': {
                            'IndexName': 'ServerTimestampIndex',
                            'KeySchema': [
                                {
                                    'AttributeName': 'ServerId',
                                    'KeyType': 'HASH'
                                },
                                {
                                    'AttributeName': 'Timestamp',
                                    'KeyType': 'RANGE'
                                },
                            ],
                            'Projection': {
                                'ProjectionType': 'ALL'
                            },
                            'ProvisionedThroughput': {
                                'ReadCapacityUnits': 5,
                                'WriteCapacityUnits': 5
                            }
                        }
                    }
                ]
            )
            print(f"Global Secondary Index 'ServerTimestampIndex' added successfully to table {self.table_name}.")
        except ClientError as e:
            print(f"Error adding Global Secondary Index: {e}")

    def query_test(self):
        response = self.table.query(
        KeyConditionExpression=Key('UserId').eq('340182205718331392'),
        ProjectionExpression='KillRecords[0].ServerId')
        print(response)

    # Query the GSI
    def solved_query_test(self):            
        
        start_date = datetime(2024, 9, 1)  # September 1, 2024
        end_date = datetime(2024, 9, 29)    # September 30, 2024
        
        response = self.table.query(
        IndexName='ServerId-index',
        KeyConditionExpression=Key('ServerId').eq('487095283222839296'),
            FilterExpression=Attr('KillRecords[0].Timestamp').between(
        start_date.isoformat(),
        end_date.isoformat()
        ),
        ProjectionExpression='UserId, TargetUserId, KillRecords[0].#ts, ServerId',
        ExpressionAttributeNames={
            '#ts': 'Timestamp'
        }
        )
        return response

if __name__ == "__main__":
    handler = DynamoDBHandler()
    result = handler.solved_query_test()
    print(result)
    
    while True:
        choice = input("Do you want to restructure the table? (yes/no): ").lower()
        if choice in ['yes', 'no']:
            break
        print("Invalid input. Please enter 'yes' or 'no'.")

    if choice == 'yes':
        handler.restructure_table()
        
    while True:
        gsi_choice = input("Do you want to add a Global Secondary Index? (yes/no): ").lower()
        if gsi_choice in ['yes', 'no']:
            break
        print("Invalid input. Please enter 'yes' or 'no'.")
    
    if gsi_choice == 'yes':
        handler.add_gsi()
    else:
        print("No changes made to the table.")