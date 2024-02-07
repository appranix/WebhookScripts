import boto3, time, os

## Command to be executed in the VM to reset the password
commands = [
    '$UserAccount = Get-LocalUser -Name "Administrator"',
    '$SecurePassword = ConvertTo-SecureString -String "AdminPassword@123" -AsPlainText -Force',
    '$UserAccount | Set-LocalUser -Password $SecurePassword'
]

active_instances = []

## Fetch the Instance ID using the IP address of the machine to be connected
def get_instance_id_by_private_ip(private_ip):
    ec2_client = boto3.client('ec2')
    
    response = ec2_client.describe_instances(
        Filters=[
            {
                'Name': 'private-ip-address',
                'Values': [str(private_ip)]
            }
        ]
    )
    
    if response['Reservations']:
        ip = response['Reservations'][0]['Instances'][0]['InstanceId']
        print(f"Found instance_id {ip} for IP: {private_ip}.")
        return response['Reservations'][0]['Instances'][0]['InstanceId']
    else:
        return None


## Trigger the Execution of thee Command in the instances
def send_command(instance_id, commands):
    ssm_client = boto3.client('ssm')
    
    # Format commands
    command_payload = {
        'commands': commands
    }
    
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunPowerShellScript",
        Parameters=command_payload
    )
    
    return response['Command']['CommandId']


## Look into the SSM Inventory ,for the recovered instances to be active
def get_inventory(instance_id):
    # Initialize the boto3 client for SSM
    ssm_client = boto3.client('ssm')
    
    # Define the filters to specify the instance ID
    filters = [{'Key': 'AWS:InstanceInformation.InstanceId', 'Values': [instance_id]}]

    try:
        # Get the inventory details for the specified instance ID
        response = ssm_client.get_inventory(
            Filters=filters
        )
        
        # Extract and return the inventory details
        if response['Entities'][0]['Data']['AWS:InstanceInformation']['Content'][0]['InstanceStatus'] == 'Active':
            return True
        else:
            return False
    
    except Exception as e:
        print(f"Error getting inventory for instance {instance_id}: {e}")
        return False

## Main Function
def lambda_handler(event, context):
    
    ## Consider using the Info from Appranix Payload
    node_ips = os.environ.get('INSTANCE_IPS').split(',')
    
    while True:
        for each_ip in node_ips:
            instance_id = get_instance_id_by_private_ip(each_ip)
            
            if instance_id is None:
                print(f"Unable to find instance id with IP {each_ip}.")
            else:
                # Get the inventory for the specified instance ID
                is_found = get_inventory(instance_id)
                    
                # Print the inventory details
                if is_found is True and instance_id not in active_instances:
                    active_instances.append(instance_id)
                    print(f"Inventory found for instance {instance_id} and the SSM agent is ACTIVE....Executing the SSM commands.....")
                    
                    # Call for triggering the Execution command in the instances
                    command_id = send_command(instance_id, commands)
                    print(f"Command executed in {instance_id} with ID: {command_id}.")
                    
                elif instance_id not in active_instances:
                    print(f"No inventory found for instance {instance_id}.Retrying in 10s....")
                else:
                    print(f"Skipping {instance_id}...Already executed the commands.")
            if len(active_instances) != len(node_ips):
                time.sleep(10)
            else:
                return {
                    'statusCode': 200,
                    'body': 'KeyPair reset completed'
                }