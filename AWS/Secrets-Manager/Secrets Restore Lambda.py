import boto3
import json
import os

def lambda_handler(event, context):
    # Get credentials from environment variables
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
    bucket_name = os.environ['BUCKET_NAME']

    # Create a session using your credentials
    client = boto3.client(
        service_name='secretsmanager',
        region_name='us-west-2',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )

    # Create an S3 client
    s3 = boto3.client('s3')

    # List all objects in the bucket
    response = s3.list_objects(Bucket=bucket_name)

    # Iterate over each object in the bucket
    for obj in response['Contents']:
        file_name = obj['Key']
        
        # Only process JSON files
        if file_name.endswith('.json'):
            # Download the file from S3
            s3.download_file(bucket_name, file_name, file_name)
            
            # Load the secret from the downloaded JSON file
            with open(file_name, 'r') as f:
                secret_dict = json.load(f)
            
            # Extract the secret name from the filename
            secret_name = file_name[:-5]  # Remove the '.json' extension
            
            # Create a new secret in AWS Secrets Manager
            response = client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(secret_dict)
            )

            print(f"Created secret: {response['Name']}")
