import boto3
import json
import datetime
import os

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)

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

    # Use the client to paginate through the parameters
    paginator = ssm.get_paginator('describe_parameters')

    for page in paginator.paginate():
        for parameter in page['Parameters']:
            response = ssm.get_parameter(Name=parameter['Name'], WithDecryption=True)
            # Save the response to a JSON file
            file_name = response['Parameter']['Name'] + '.json'
            with open(file_name, 'w') as f:
                json.dump(response['Parameter'], f, cls=DateTimeEncoder)
            
            # Upload the file to S3
            with open(file_name, 'rb') as data:
                s3.upload_fileobj(data, os.environ['BUCKET_NAME'], file_name)
