import boto3, os, json, logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## Env Variables
## Consider using the Appranix payload information
replication_lambda = os.environ.get('REPLICATION_LAMBDA')
restore_lambda = os.environ.get('RESTORE_LAMBDA')
replication_regions = os.environ.get('REPLICATION_REGIONS').split(',')
account_arns = os.environ.get('ACCOUNT_ARNS').split(',')

def handle_secret_manager_error(secret_name, error):
    error_code = error.response['Error']['Code']
    error_message = error.response['Error']['Message']
    if error_code == 'AccessDeniedException':
        logging.error(f"Access denied for secret {secret_name}: {error_message}")
    elif error_code == 'InvalidParameterException':
        logging.error(f"Invalid params for the secret {secret_name}: {error_message}")
    elif error_code == 'InvalidRequestException':
        logging.warning(f"Invalid request for secret {secret_name}: {error_message}. Skipping....")
    else:
        logging.error(f"Error fetching secret {secret_name}: {error_message}")
    raise error

def get_secret(secrets_to_backup):

    # Create a Secrets Manager client
    secret_manager_client = boto3.client('secretsmanager')
    
    # Create a dictionary to store key-value pairs
    backup_secrets_data = {}
    for secret_name in secrets_to_backup:
        try:
            get_secret_value_response = secret_manager_client.get_secret_value(
                SecretId=secret_name
            )
            backup_secrets_data[secret_name] = {
                "SecretString": get_secret_value_response["SecretString"],
                "VersionId": get_secret_value_response["VersionId"]
            }
        except ClientError as e:
            handle_secret_manager_error(secret_name, e)
    
    return json.dumps(backup_secrets_data, indent=4)

def get_restore_secret_details(credentials, secrets_to_restore):
    secret_manager_client = boto3.client('secretsmanager',aws_access_key_id=credentials['AccessKeyId'], aws_secret_access_key=credentials['SecretAccessKey'], aws_session_token=credentials['SessionToken'], region_name="us-east-1")

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
    
    return json.dumps(restoring_secrets_data,indent=4)

## Invoke Lambdas in the operational regions to replicate/restore the secrets
def invoke_lambda_function(credentials, lambda_function_name, secret_details, region):
    lambda_client = boto3.client('lambda', aws_access_key_id=credentials['AccessKeyId'], aws_secret_access_key=credentials['SecretAccessKey'], aws_session_token=credentials['SessionToken'], region_name=region)

    try:
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(secret_details)
        )

        logging.info(f"Lambda function '{lambda_function_name}' invoked successfully in region '{region}'.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logging.error(f"Lambda function '{lambda_function_name}' not found in region '{region}'.")
        else:
            logging.error(f"Failed to invoke Lambda function '{lambda_function_name}' in region '{region}': {str(e)}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")
  
def lambda_handler(event, context):
    if "recoveryStatus" in event.keys() and event["recoveryStatus"] == "RECOVERY_COMPLETED":
        for account_arn in account_arns:
            sts_client = boto3.client('sts')
            response = sts_client.assume_role(RoleArn=account_arn, RoleSessionName='SecretManagerRestore')
            credentials = response['Credentials']
            for region in replication_regions:
                invoke_lambda_function(credentials, restore_lambda, event, region)
        return {
            'statusCode': 200,
            'body': 'Secret Manager restoration completed'
        }
    primary_region_secrets = get_secret(event["secretsToBackup"])

    for account_arn in account_arns:
        sts_client = boto3.client('sts')
        response = sts_client.assume_role(RoleArn=account_arn, RoleSessionName='SecretManagerReplication')
        credentials = response['Credentials']
        for region in replication_regions:
            invoke_lambda_function(credentials, replication_lambda, primary_region_secrets, region)

    return {
        'statusCode': 200,
        'body': 'Secret Manager backup completed'
    }