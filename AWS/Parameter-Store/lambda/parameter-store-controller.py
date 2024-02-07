import boto3, os, json
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## Env Variables
## Consider using the Appranix payload information
replication_lambda = os.environ.get('REPLICATION_LAMBDA')
restore_lambda = os.environ.get('RESTORE_LAMBDA')
operational_regions = os.environ.get('OPERATIONAL_REGIONS').split(',')
account_arns = os.environ.get('ACCOUNT_ARNS').split(',')
parameters_to_backup = os.environ.get('PARAMETERS_TO_BACKUP').split(',')


## Get Primary Region Parameter Store Values
def get_parameters(event):
    ssm_client = boto3.client('ssm')

    # Create a dictionary to store key-value pairs
    backup_parameters_data = {}
    
    # Iterate through each parameter and store in the dictionary
    for parameter_name in parameters_to_backup:
        try:        
            parameter_response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)['Parameter']
            parameter_value = {
                'Value': parameter_response['Value'],
                'Type': parameter_response['Type'],
                'Version': parameter_response['Version']
            }
            backup_parameters_data[parameter_name] = parameter_value

        except Exception as e:
            logger.error(f"Error while retrieving parameters: {e}")

    return {
        'statusCode': 200,
        'body': json.dumps(backup_parameters_data)
    }

## Invoke Lambdas in the operational regions to replicate the parameters
def invoke_lambda_function(credentials, lambda_function_name, parameter_details, region):
    lambda_client = boto3.client('lambda', aws_access_key_id=credentials['AccessKeyId'], aws_secret_access_key=credentials['SecretAccessKey'], aws_session_token=credentials['SessionToken'], region_name=region)

    try:
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(parameter_details)
        )
        
        logging.info(f"Lambda function '{lambda_function_name}' invoked successfully in region '{region}'.")
        
        # Read the content from the StreamingBody
        body_content = response['Payload'].read()
    
        # Decode the content (assuming it's in UTF-8 encoding)
        decoded_content = body_content.decode('utf-8')
        
        # Parse the decoded content as JSON
        json_content = json.loads(body_content)
        
        # global_params_mapped_payload[account_arn][region] = json_content['body']
        logging.debug(f"Lambda response payload: {json_content['body']}")      
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logging.error(f"Lambda function '{lambda_function_name}' not found in region '{region}'.")
        else:
            logging.error(f"Failed to invoke Lambda function '{lambda_function_name}' in region '{region}': {str(e)}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")

def get_restore_parameter_details(parameters_to_restore):
    ssm_client = boto3.client('ssm')

    # Create a dictionary to store key-value pairs
    restoring_parameters_data = {}
    
    # Iterate through each parameter, get the values and stores in the dictionary
    for parameter_name,parameter_version in parameters_to_restore.items():
        try:
            parameter_response = ssm_client.get_parameter_history(Name=parameter_name, WithDecryption=True)
            parameter_found = False
            for parameter_history in parameter_response['Parameters']:
                if parameter_history['Name'] == parameter_name and parameter_history['Version'] == parameter_version:
                    parameter_value = {
                        'Value': parameter_history['Value'],
                        'Type': parameter_history['Type']
                    }
                    restoring_parameters_data[parameter_name] = parameter_value
                    parameter_found = True
            if not parameter_found:
                logger.error(f"Parameter {parameter_name} version {parameter_version} not found")
        except Exception as e:
            logger.error(f"Error while retrieving parameters: {e}")
            return {'statusCode': 500, 'body': f'Error while retrieving parameters: {e}'}
    
    logging.info(f"{restoring_parameters_data}")
    
    return {
        'statusCode': 200,
        'body': json.dumps(restoring_parameters_data)
    }

## Main function
def lambda_handler(event, context):
    
    '''
    ### Uncomment the following set of lines in case of including the restoration script here to orchestrate in a single file.
    if "recoveryStatus" in event.keys() and event["recoveryStatus"] == "RECOVERY_COMPLETED":
        restore_params_details = get_restore_parameter_details(json.loads(event["parameters_to_restore"]))["body"]

        for account_arn in account_arns:
            sts_client = boto3.client('sts')
            response = sts_client.assume_role(RoleArn=account_arn, RoleSessionName='ParameterStoreRestore')
            credentials = response['Credentials']
            for region in operational_regions:
                invoke_lambda_function(credentials, restore_lambda, restore_params_details, region)
        
        return {
            'statusCode': 200,
            'body': 'Parameter Store restoration completed'
        }
    '''

    primary_region_params = get_parameters(event)

    for account_arn in account_arns:
        sts_client = boto3.client('sts')
        response = sts_client.assume_role(RoleArn=account_arn, RoleSessionName='ParameterStoreReplication')
        credentials = response['Credentials']
        for region in operational_regions:
            invoke_lambda_function(credentials, replication_lambda, primary_region_params['body'], region)

    return {
        'statusCode': 200,
        'body': 'Parameter Store backup completed'
    }