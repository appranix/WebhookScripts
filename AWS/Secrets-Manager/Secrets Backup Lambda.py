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

    response = client.list_secrets()

    for secret in response['SecretList']:
        secret_name = secret['Name']
        secret_value_response = client.get_secret_value(SecretId=secret_name)
        
        # Depending on whether the secret is a string or binary, one of these fields will be populated
        if 'SecretString' in secret_value_response:
            secret_value = secret_value_response['SecretString']
            secret_dict = json.loads(secret_value)

            file_name = f'{secret_name}.json'
            with open(file_name, 'w') as f:
                json.dump(secret_dict, f)
            
            # Upload the file to S3
            with open(file_name, 'rb') as data:
                s3.upload_fileobj(data, bucket_name, file_name)

        else:
            # Uncomment this line if you have binary secrets
            # secret_value = base64.b64decode(secret_value_response['SecretBinary'])
            pass
