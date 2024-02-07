import boto3, json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## Describe the backup parameter details in the local region
def get_parameters(parameters_to_replicate):
    ssm_client = boto3.client('ssm')

    # Create a dictionary to store key-value pairs
    replicated_parameters_data = {}
    
    try:
        # Iterate through each parameter and store in the dictionary
        for parameter_name in parameters_to_replicate:
            parameter_response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)['Parameter']
            parameter_value = {
                'Value': parameter_response['Value'],
                'Type': parameter_response['Type'],
                'Version': parameter_response['Version']
            }
            replicated_parameters_data[parameter_name] = parameter_value

    except Exception as e:
        logger.error(f"Error while retrieving parameters: {e}")
    
    return {
        'statusCode': 200,
        'body': json.dumps(replicated_parameters_data)
    }

def lambda_handler(event, context):
    
    backedup_params = get_parameters(json.loads(event))
    update_ssm_parameters(json.loads(event), json.loads(backedup_params['body']))
    
    return {
        'statusCode': 200,
        'body': json.dumps(get_parameters(json.loads(event))['body'])
    }
    
    
def update_ssm_parameters(primary_parameters, secondary_parameters):
    ssm_client = boto3.client('ssm')
    
    for key, primary_value in primary_parameters.items():
        if key not in secondary_parameters:
            logging.info(f"Replicating parameter {key}...")
            
            # Create the parameter if it doesn't exist in the secondary region
            ssm_client.put_parameter(
                Name=key,
                Value=primary_value.get('Value'),
                Type=primary_value.get('Type'),
                Overwrite=False
            )
        elif key in secondary_parameters:
            if isinstance(secondary_parameters[key], dict):
                secondary_value = secondary_parameters[key].get('Value')
            else:
                logging.info(f"Unexpected type for key {key}: {type(secondary_parameters[key])}")
                continue

            primary_value_value = primary_value.get('Value')

            if isinstance(secondary_value, str) and isinstance(primary_value_value, str) and secondary_value != primary_value_value:
                logging.info(f"Updating parameter {key}.....")
                
                # Update the parameter if values differ between primary payload
                ssm_client.put_parameter(
                    Name=key,
                    Value=primary_value.get('Value'),
                    Type=primary_value.get('Type'),
                    Overwrite=True
                )
            else:
                logging.info(f"Values unchanged..Skipping parameter {key}.")