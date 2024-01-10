import boto3
import json, os

def lambda_handler(event, context):
    print(event)
    # Initialize the Step Functions client
    stepfunctions_client = boto3.client('stepfunctions')
    
    # Define the Step Functions state machine ARN
    state_machine_arn = os.environ.get('STEP_FUNCTION_ARN')
    
    try:
        # Start the Step Functions execution
        response = stepfunctions_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(event)  # Pass the input event to the state machine
        )
        
        # Extract and return the execution ARN
        execution_arn = response['executionArn']
        return '200'
    
    except Exception as e:
        print(f"Error starting Step Functions execution: {e}")
        return '500'
