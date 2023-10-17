import boto3
import json
import os

def lambda_handler(event, context):
    # Create a session using your credentials
    session = boto3.Session(
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
    )

    # Create a client using the session in a different region
    sqs = session.client('sqs', region_name='us-east-2')

    # Create an S3 client
    s3 = session.client('s3')

    # Specify your bucket name and folder name
    bucket_name = 'sqs-test-bucket-001'
    folder_name = 'timeline_id'+'/'

    # List all objects in the folder
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=folder_name)

    # Iterate through each file in the folder
    for obj in response['Contents']:
        # Get the file key
        file_key = obj['Key']

        # Download the JSON file from S3
        file_object = s3.get_object(Bucket=bucket_name, Key=file_key)
        file_content = file_object['Body'].read().decode('utf-8')
        user_attributes = json.loads(file_content)

        # Specify your new queue name by appending 'ax' to the original queue name
        new_queue_name = 'ax-'+user_attributes['QueueArn'].split(':')[-1]

        # Create the SQS queue with the user-provided attributes
        response = sqs.create_queue(
            QueueName=new_queue_name,
            Attributes={
                'DelaySeconds': user_attributes['DelaySeconds'],
                'MaximumMessageSize': user_attributes['MaximumMessageSize'],
                'MessageRetentionPeriod': user_attributes['MessageRetentionPeriod'],
                'Policy': user_attributes['Policy'],
                'ReceiveMessageWaitTimeSeconds': user_attributes['ReceiveMessageWaitTimeSeconds'],
                'VisibilityTimeout': user_attributes['VisibilityTimeout']
            }
        )

        print("Queue {} created with URL: {}".format(new_queue_name, response['QueueUrl']))
