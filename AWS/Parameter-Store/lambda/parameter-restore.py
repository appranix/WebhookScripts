import boto3, os, json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

source_account_arn = os.environ.get('SOURCE_ACCOUNT_ARN')

sts_client = boto3.client('sts')
response = sts_client.assume_role(RoleArn=source_account_arn, RoleSessionName='ParameterStoreReplication')
credentials = response['Credentials']

def get_restore_parameter_details(parameters_to_restore):
    ssm_client = boto3.client('ssm', aws_access_key_id=credentials['AccessKeyId'], aws_secret_access_key=credentials['SecretAccessKey'], aws_session_token=credentials['SessionToken'])

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
    event = get_restore_parameter_details(event)

    ssm_client = boto3.client('ssm')
    for restoring_parameters_key,restoring_parameters_values in event.items():
        ssm_client.put_parameter(
            Name=restoring_parameters_key,
            Value=restoring_parameters_values.get('Value'),
            Type=restoring_parameters_values.get('Type'),
            Overwrite=True
        )
    
    return {
        'statusCode': 200,
        'body': 'Parameter Store Restoration Completed'
    }