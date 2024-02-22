import boto3, os, json, logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

source_account_arn = os.environ.get('SOURCE_ACCOUNT_ARN')

def get_secret(secrets_to_restore):

    # Create a Secrets Manager client
    secret_manager_client = boto3.client('secretsmanager')
    
    # Create a dictionary to store key-value pairs
    secrets_data = {}
    for secret_name in secrets_to_restore:
        try:
            get_secret_value_response = secret_manager_client.get_secret_value(
                SecretId=secret_name
            )
            secrets_data[secret_name] = {
                "SecretString": get_secret_value_response["SecretString"],
                "VersionId": get_secret_value_response["VersionId"]
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDeniedException':
                logging.error(f"Access denied for secret {secret_name}: {e}")
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                logging.error(f"The request had invalid params for the secret {secret_name}: {e}")
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                logging.warning(f"Invalid request for secret {secret_name}: {str(e)}. Skipping....")
            else:
                logging.error(f"Error fetching secret {secret_name}: {str(e)}")
    
    return secrets_data


def get_restore_secret_details(credentials, secrets_to_restore, primary_region):
    secret_manager_client = boto3.client('secretsmanager',aws_access_key_id=credentials['AccessKeyId'], aws_secret_access_key=credentials['SecretAccessKey'], aws_session_token=credentials['SessionToken'], region_name=primary_region)

    # Create a dictionary to store key-value pairs
    restoring_secrets_data = {}

    # Iterate through each secrets, get the values and stores in the dictionary
    for secret_name,secret_version in secrets_to_restore.items():
        try:
            secrets_response = secret_manager_client.get_secret_value(
                SecretId=secret_name,
                VersionId=secret_version
            )
            secrets_value = {
                'SecretString': secrets_response['SecretString'],
                'VersionId': secrets_response['VersionId']
            }
            restoring_secrets_data[secret_name] = secrets_value

        except Exception as e:
            logger.error(f"Error while retrieving secrets: {e}")
    
    return restoring_secrets_data

def restore_secrets(primary_region_secrets, local_region_secrets):
    secret_manager_client = boto3.client('secretsmanager')
    for secret_key,secret_value in primary_region_secrets.items():
        logging.info(f"Processing the {secret_key} for restoration...")
        try:
            if secret_key not in local_region_secrets:
                logging.info(f"Restoring the secret {secret_key} in the region.")
                secret_manager_client.create_secret(Name=secret_key,SecretString=str(secret_value))
            elif secret_key in local_region_secrets and isinstance(secret_value,dict):
                local_secret_value = local_region_secrets[secret_key]["SecretString"]
                if str(secret_value["SecretString"]) != str(local_secret_value):
                    logging.info(f"Restoring the value of secret {secret_key} with {secret_value['SecretString']}")
                    secret_manager_client.put_secret_value(SecretId=secret_key,SecretString=str(secret_value['SecretString']))
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterException' and 'replica' in e.response['Error']['Message']:
                logging.warning(f"Operation not permitted on a replica secret. Call must be made in primary secret's region..Skipping {secret_key}.")
            else:
                raise e
    logging.info("Restored the Secret Manager versions as of primary region..")

def lambda_handler(event, context):
    local_region_secrets = get_secret(event["secretsToRestore"])
    sts_client = boto3.client('sts')
    response = sts_client.assume_role(RoleArn=source_account_arn, RoleSessionName='SecretManagerRestore')
    credentials = response['Credentials']
    restore_secrets_details = get_restore_secret_details(credentials, event["secretsToRestore"], event["primaryRegion"])
    restore_secrets(restore_secrets_details, local_region_secrets)  
    return {
        'statusCode': 200,
        'body': 'Secret Manager restoration completed'
    }