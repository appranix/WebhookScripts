import boto3, time, os

commands = [
    'Write-Host "Running ipconfig on the remote machine..."',
    'ipconfig',
    'Write-Host "Installing iSCSI Target Server role..."',
    'Install-WindowsFeature -Name FS-iSCSITarget-Server',
    'Set-Service -Name MSiSCSI -StartupType Automatic',
    'Start-Service MSiSCSI',
    'Get-NetFirewallServiceFilter -Service msiscsi | Get-NetFirewallRule | Enable-NetFirewallRule',
    f'New-IscsiTargetPortal -TargetPortalAddress {os.environ.get('ISCSI_IP')}',
    'Get-IscsiTarget | Connect-IscsiTarget',
    'Get-Disk',
    'Get-IscsiSession | Register-IscsiSession',
    'Get-Disk -Number 1 | Initialize-Disk -PartitionStyle GPT –Passthru | New-Partition –AssignDriveLetter –UseMaximumSize | Format-Volume -FileSystem ntfs -Confirm:$false',
    'Get-Volume -DriveLetter D | Set-Volume -NewFileSystemLabel "sqldisk"',
    'Start-Sleep -Seconds 10',
    'Start-Service MSSQLSERVER'

]

iis_starter_command = [
    'Start-Sleep -Seconds 30',
    'cd "C:\\Users\\Administrator.NEWDOMAIN\\Downloads\\eShopOnWeb-main\\eShopOnWeb-main\\src\\Web"',
    'dotnet run'
    ]


active_instances = []

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

def iis_initiate():
    
    iis_ips = os.environ.get('IIS_IPS').split(',')
    
    for each_ip in iis_ips: 
        instance_id = get_instance_id_by_private_ip(each_ip)
        
        if instance_id is None:
                print(f"Unable to find IIS instance id with IP {each_ip}.")
        else:
            # Get the inventory for the specified instance ID
            is_found = get_inventory(instance_id)
                
            # Print the inventory details
            if is_found is True and instance_id not in active_instances:
                active_instances.append(instance_id)
                print(f"Inventory found for IIS instance {instance_id} and the SSM agent is ACTIVE....Executing the startup commands.....")
                
                command_id = send_command(instance_id, iis_starter_command)
                print(f"Command executed in IIS {instance_id} with ID: {command_id}.")
                
            elif instance_id not in active_instances:
                print(f"No inventory found for IIS instance {instance_id}.Retrying in 10s....")
            else:
                print(f"Skipping IIS {instance_id}...Already executed the commands.")
        if len(active_instances) != len(iis_ips):
            time.sleep(10)
        else:
            return {
                "statusCode": 200
            }


def lambda_handler(event, context):
    node_ips = os.environ.get('NODE_IPS').split(',')
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
                    print(f"Inventory found for instance {instance_id} and the SSM agent is ACTIVE....Executing the mount commands.....")
                    
                    command_id = send_command(instance_id, commands)
                    print(f"Command executed in {instance_id} with ID: {command_id}.")
                    
                elif instance_id not in active_instances:
                    print(f"No inventory found for instance {instance_id}.Retrying in 10s....")
                else:
                    print(f"Skipping {instance_id}...Already executed the commands.")
            if len(active_instances) != len(node_ips):
                time.sleep(10)
            else:
                iis_initiate()
                return {
                    "statusCode": 200
                }
