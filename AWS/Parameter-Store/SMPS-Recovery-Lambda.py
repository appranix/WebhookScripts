import boto3
import json
import os

def lambda_handler(event, context):
    # Get AWS credentials from environment variables
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']

    # Create a session using your credentials
    session = boto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )

    # Create an SSM and S3 client using your session
    ssm = session.client('ssm', region_name='us-west-2')
    s3 = session.client('s3')

    # Get bucket name from environment variable
    bucket_name = os.environ['BUCKET_NAME']

    # List all objects in the bucket
    response = s3.list_objects_v2(Bucket=bucket_name)

    # Iterate through each file in the bucket
    for obj in response['Contents']:
        # Check if the file is a JSON file
        if obj['Key'].endswith('.json'):
            # Download the JSON file from S3
            file_object = s3.get_object(Bucket=bucket_name, Key=obj['Key'])
            file_content = file_object['Body'].read().decode('utf-8')
            json_content = json.loads(file_content)

            # Use the client to create a parameter
            response = ssm.put_parameter(
                Name='ax-'+json_content['Name'],
                Value=json_content['Value'],
                Type=json_content['Type'],
                Overwrite=True  # Set to True to overwrite an existing parameter
            )

            # Print the response from AWS
            print(response)
