import json
import os
import time
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import logging
from urllib.request import urlopen

logger = logging.getLogger()
logger.setLevel(logging.INFO)
s3 = boto3.client('s3')
bucket_name = os.environ.get('BUCKET_NAME')
region = os.environ.get('BUCKET_REGION')
object_name = os.environ.get('BUCKET_OBJECT_ID')


def validateEventPayload(event):
    for key in event.keys():
        if key == "body":
            logger.info("Found body parameter block")
            return json.loads(event[key])
    logger.info("Event does not has the body block")
    return event

def get_recovered_vpc_id(event):
    logger.info(event)
    data_dictionary = validateEventPayload(event)
    if data_dictionary["recoveryStatus"] == "RECOVERY_COMPLETED":
        url = data_dictionary["resourceMapping"]["recoveredMetadataPath"]
        response = urlopen(url)
        payload = json.loads(response.read())
        logger.info(payload)
        for item in payload:
            # Loop through the key-value pairs in each dictionary
            for key, value in item.items():
                # Check if the dictionary contains 'vpcId' key
                if 'vpcId' in value[0]:
                    return value[0]['vpcId']
            else:
                return None


def create_bucket_if_not_exist(region):
    try:
        s3.head_bucket(Bucket=bucket_name)
        logger.info('Bucket "{}" already exists'.format(bucket_name))
    except ClientError as e:
        try:
            if e.response['Error']['Code'] == '404' or e.response['Error']['Code'] == '403':
                if region == 'us-east-1':
                    s3.create_bucket(ACL='private', Bucket=bucket_name)
                else:
                    s3.create_bucket(ACL='private', Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

                s3.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={'Status': 'Enabled'})
                s3.put_bucket_encryption(
                    Bucket=bucket_name,
                    ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}
                )

                retention_period = 365
                s3.put_bucket_lifecycle_configuration(
                    Bucket=bucket_name,
                    LifecycleConfiguration={
                        "Rules": [
                            {
                                "Expiration": {"Days": retention_period},
                                "ID": "S3 Deletion Rule",
                                "Filter": {"Prefix": ""},
                                "Status": "Enabled",
                                "NoncurrentVersionExpiration": {"NoncurrentDays": retention_period}
                            }
                        ]
                    }
                )

                s3.put_bucket_policy(
                    Bucket=bucket_name,
                    Policy="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"Stmt1566916793194\",\"Action\":\"s3:*\",\"Effect\":\"Deny\","
                        "\"Resource\":\"arn:aws:s3:::" + bucket_name + "/*\",\"Condition\":{\"Bool\":{\"aws:SecureTransport\":\"false\"}},"
                                                                        "\"Principal\":\"*\"}]} "
                )

                logger.info('Created the bucket "{}"'.format(bucket_name))
            else:
                logger.info(f"Different Error Code {e.response['Error']['Code']}")
        except Exception as e:
            logger.info(f"Entirely Different Error Mesage {e.message}")

def lambda_handler(event, context):
    recovered_vpc_id = get_recovered_vpc_id(event)
    logging.info(f'Extracted the recovered VPC Id {recovered_vpc_id}....')
    file = {'VPC-id' : recovered_vpc_id}
    create_bucket_if_not_exist(region)
    s3.put_object(Body=json.dumps(file).encode(), Bucket=bucket_name, Key=object_name)
    logging.info(f'Uploaded the recovered VPC Id {recovered_vpc_id} to the Bucket {bucket_name}....')
    logging.info('Execution Successful....')
    return '200'