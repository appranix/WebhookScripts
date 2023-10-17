import boto3
import json
import os

def lambda_handler(event, context):
    # Create a session using your credentials
    session = boto3.Session(
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
    )

    # Create a client using the session
    sqs = session.client('sqs', region_name='us-west-2')
    s3 = session.client('s3')

    # Specify your bucket name
    bucket_name = 'sqs-test-bucket-001'
    folder_name = 'timeline_id'

    # List SQS queues
    response = sqs.list_queues()

    # Print out each queue
    for queue_url in response['QueueUrls']:
        print(queue_url)
        # Get queue attributes
        response = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['All']
        )

        # Save the response to a JSON file
        file_name = response['Attributes']['QueueArn'] + '.json'
        with open(file_name, 'w') as f:
            json.dump(response['Attributes'], f)

        # Upload the file to S3
        with open(file_name, 'rb') as data:
            s3.upload_fileobj(data, bucket_name, folder_name+'/'+file_name)
