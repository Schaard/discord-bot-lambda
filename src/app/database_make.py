import boto3
from botocore.exceptions import ClientError
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

if __name__ == "__main__":
    handler = DynamoDBHandler()
    
    while True:
        choice = input("Do you want to restructure the table? (yes/no): ").lower()
        if choice in ['yes', 'no']:
            break
        print("Invalid input. Please enter 'yes' or 'no'.")

    if choice == 'yes':
        handler.restructure_table()
    else:
        print("No changes made to the table.")
