import boto3, json
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create a Secrets Manager client
secret_manager_client = boto3.client('secretsmanager')

def get_secrets(secrets_to_replicate):
    # Create a dictionary to store key-value pairs
    backup_secrets_data = {}
    for secret_name, secret_details in secrets_to_replicate.items():
        try:
            get_secret_value_response = secret_manager_client.get_secret_value(
                SecretId=secret_name
            )
            backup_secrets_data[secret_name] = {
                "SecretString": get_secret_value_response["SecretString"],
                "VersionId": get_secret_value_response["VersionId"]
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logging.info(f"Creating secert value: {secret_details["SecretString"], secret_details["VersionId"]}")
                logging.warning(f"Secret {secret_name} not found in Secrets Manager. Creating....")
                # Create the secret here or handle it as needed
                if "SecretString" in secret_details and "VersionId" in secret_details:
                    create_secret_response = secret_manager_client.create_secret(
                        Name=secret_name,
                        SecretString=str(secret_details["SecretString"]),
                        ClientRequestToken=secret_details["VersionId"]
                    )
                    backup_secrets_data[secret_name] = {
                        "SecretString": secret_details["SecretString"],
                        "VersionId": create_secret_response["VersionId"]
                    }
                else:
                    logging.error(f"Missing required fields in secrets_to_replicate for secret {secret_name}.")
                    return {
                        "statusCode": 400,
                        "message": f"Missing required fields in secrets_to_replicate for secret {secret_name}."
                    }
            elif e.response['Error']['Code'] == 'AccessDeniedException':
                logging.error(f"Error Occurred: {e}")
                return {
                    "statusCode": 403,
                    "message": f"Access denied for secret {secret_name}."
                }
            else:
                logging.error(f"Error fetching secret {secret_name}: {str(e)}")
                return {
                    "statusCode": 400,
                    "message": f"Error fetching secret {secret_name}: {str(e)}"
                }
    logging.info(f"Fetched all the secret details: {backup_secrets_data}")
    return backup_secrets_data

def update_secrets(primary_region_secrets, local_region_secrets):
    primary_region_secrets = json.loads(primary_region_secrets)
    for secret_key,secret_value in primary_region_secrets.items():
        logging.info(f"Processing the {secret_key} for replication...")
        try:
            if secret_key not in local_region_secrets:
                logging.info(f"Creating secret {secret_key} in the region.")
                secret_manager_client.create_secret(Name=secret_key,SecretString=str(secret_value))
            elif secret_key in local_region_secrets and isinstance(secret_value,dict):
                local_secret_value = local_region_secrets[secret_key]["SecretString"]
                if str(secret_value["SecretString"]) != str(local_secret_value):
                    logging.info(f"Updating the value of secret {secret_key} with {json.dumps(secret_value['SecretString'])}")
                    secret_manager_client.put_secret_value(SecretId=secret_key,SecretString=str(json.dumps(secret_value['SecretString'])))
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterException' and 'replica' in e.response['Error']['Message']:
                logging.warning(f"Operation not permitted on a replica secret. Call must be made in primary secret's region..Skipping {secret_key}.")
            else:
                raise e

    logging.info("Replicated the Secret Manager values as of primary region values..")

def lambda_handler(event, context):
    secret_details = get_secrets(json.loads(event))
    update_secrets(event, secret_details)
    
    return {
        'statusCode': 200,
        'body': json.dumps(get_secrets(json.loads(event)))
    }