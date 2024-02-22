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
            logging.info(get_secret_value_response)
            backup_secrets_data[secret_name] = {
                "SecretString": get_secret_value_response["SecretString"],
                "VersionId": get_secret_value_response["VersionId"]
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDeniedException':
                logging.error(f"Access denied for secret {secret_name}: {e}")
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                logging.error(f"The request had invalid params for the secret {secret_name}: {e}")
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                logging.warning(f"Invalid request for secret {secret_name}: {str(e)}. Skipping.")
            else:
                logging.error(f"Error fetching secret {secret_name}: {str(e)}")
    
    return json.dumps(backup_secrets_data, indent=4)

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