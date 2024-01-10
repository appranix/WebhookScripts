import boto3, os
import logging, json, time
from urllib.request import urlopen

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# Initialize the Boto3 client for AWS services
ec2_client = boto3.client('ec2')

def validateEventPayload(event):
    for key in event.keys():
        if key == "body":
            logger.info("Found body parameter block")
            return json.loads(event[key])
    logger.info("Event does not has the body block")
    return event

def get_recovered_vpc_id(event):
    logger.info(event)
    data_dictionary = validateEventPayload(event)
    if data_dictionary["recoveryStatus"] == "RECOVERY_COMPLETED":
        url = data_dictionary["resourceMapping"]["recoveredMetadataPath"]
        response = urlopen(url)
        payload = json.loads(response.read())
        logger.info(payload)
        for item in payload:
            # Loop through the key-value pairs in each dictionary
            for key, value in item.items():
                # Check if the dictionary contains 'vpcId' key
                if 'vpcId' in value[0]:
                    return value[0]['vpcId']
            else:
                return None

# Create Transit Gateway
def create_transit_gateway():
    response = ec2_client.create_transit_gateway(
        Description='BlueXP-OnTapTgw',
        TagSpecifications=[
            {
                'ResourceType': 'transit-gateway',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'BlueXP-OnTapTgw'
                    },
                ]
            },
        ]
    )
    # Polling loop to check the status
    while True:
        tgw_id = response['TransitGateway']['TransitGatewayId']
        tgw_info = ec2_client.describe_transit_gateways(TransitGatewayIds=[tgw_id])
        state = tgw_info['TransitGateways'][0]['State']
        
        if state == 'available':
            break
        
        print(f"Transit Gateway {tgw_id} is in {state} state. Waiting...")
        time.sleep(5)
    return response['TransitGateway']['TransitGatewayId']

# Attach VPCs to Transit Gateway
def attach_vpc_to_transit_gateway(tgw_id, vpc_id, subnet_ids):
    response = ec2_client.create_transit_gateway_vpc_attachment(
        TransitGatewayId=tgw_id,
        VpcId=vpc_id,
        SubnetIds=subnet_ids,
        TagSpecifications=[
            {
                'ResourceType': 'transit-gateway-attachment',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': f'{vpc_id}-TgwAttachment'
                    },
                ]
            },
        ]
    )
    while True:
        tgw_attach_id=response['TransitGatewayVpcAttachment']['TransitGatewayAttachmentId']
        tgw_info = ec2_client.describe_transit_gateway_attachments(TransitGatewayAttachmentIds=[tgw_attach_id])
        state = tgw_info['TransitGatewayAttachments'][0]['State']
        
        if state == 'available':
            break
        
        print(f"Transit Gateway Attachment {tgw_attach_id} is in {state} state. Waiting...")
        time.sleep(5)
    return response['TransitGatewayVpcAttachment']['TransitGatewayAttachmentId']

def list_route_tables(vpc_id):
    # Initialize the boto3 client for EC2
    ec2_client = boto3.client('ec2')
    
    try:
        # Describe route tables for the specified VPC
        response = ec2_client.describe_route_tables(
            Filters=[
                {
                    'Name': 'vpc-id',
                    'Values': [vpc_id]
                }
            ]
        )
        
        # Extract and return the route table IDs
        route_table_ids = [route_table['RouteTableId'] for route_table in response['RouteTables']]
        return route_table_ids
    
    except Exception as e:
        print(f"Error listing route tables for VPC {vpc_id}: {e}")
        return None


def add_transit_gateway_route(route_table_id, transit_gateway_id, destination_cidr_block):
    # Initialize the boto3 client for EC2
    ec2_client = boto3.client('ec2')
    
    try:
        # Create a route to the transit gateway in the route table
        response = ec2_client.create_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock=destination_cidr_block,
            TransitGatewayId=transit_gateway_id
        )
        
        print(f"Added route {destination_cidr_block} to route table {route_table_id} for transit gateway {transit_gateway_id}.")
        return True
    
    except Exception as e:
        print(f"Error adding route to route table {route_table_id}: {e}")
        return False

    
def get_subnet_ids(vpc_id):
    # Initialize the boto3 client for EC2
    ec2_client = boto3.client('ec2')
    # Get all subnets for the specified VPC
    response = ec2_client.describe_subnets(
        Filters=[
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }
        ]
    )
    
    # Extract and return the subnet IDs
    subnet_ids = [subnet['SubnetId'] for subnet in response['Subnets']]
    return subnet_ids
    
    
def get_unique_subnets_per_az(vpc_id):
    # Describe subnets in the VPC
    subnets_response = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])

    subnets_by_az = {}
    # Collect unique subnets for each AZ
    for subnet in subnets_response['Subnets']:
        az = subnet['AvailabilityZone']
        subnet_id = subnet['SubnetId']

        # If the AZ is not yet in the dictionary, add it with the subnet
        if az not in subnets_by_az:
            subnets_by_az[az] = subnet_id

    # Convert the dictionary values (subnet IDs) to a list
    return list(subnets_by_az.values())

def add_route_to_vpc_route_table(vpc_id, destination_cidr_block, tgw_id):
    route_table = ec2_client.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    route_table_id = route_table['RouteTables'][0]['RouteTableId']
    
    ec2_client.create_route(
        DestinationCidrBlock=destination_cidr_block,                                                                        
        RouteTableId=route_table_id,
        TransitGatewayId=tgw_id
    )

# Example usage
def lambda_handler(event, context):
    # Create Transit Gateway
    tgw_id = create_transit_gateway()

    # Attach VPC1 to Transit Gateway
    vpc1_id = os.environ.get('BLUEXP_VPC_ID')
    subnet_ids_1 = get_unique_subnets_per_az(vpc1_id)
    if subnet_ids_1 is not None:
        attachment_id_vpc1 = attach_vpc_to_transit_gateway(tgw_id, vpc1_id, subnet_ids_1)
    else:
        print(f"Unable to attach Tgw attachment for VPC: {vpc1_id} with subnet {subnet_ids_1}.")
    
    route_table_ids = list_route_tables(vpc1_id)
    
    if route_table_ids is not None:
        # Add transit gateway routes to all route tables
        for route_table_id in route_table_ids:
            add_transit_gateway_route(route_table_id, tgw_id, '10.0.0.0/16')
    else:
        print(f"Unable to add route table entry for VPC: {vpc1_id} with routes of {route_table_ids}.")

    # Attach the recovered VPC to Transit Gateway
    vpc2_id = get_recovered_vpc_id(event)
    subnet_ids_2 = get_unique_subnets_per_az(vpc2_id)
    if subnet_ids_2 is not None:
        attachment_id_vpc2 = attach_vpc_to_transit_gateway(tgw_id, vpc2_id, subnet_ids_2)
    else:
        print(f"Unable to attach Tgw attachment for VPC: {vpc2_id} with subnet {subnet_ids_2}.")
       
    route_table_ids = list_route_tables(vpc2_id)
    
    if route_table_ids is not None:
        # Add transit gateway routes to all route tables
        for route_table_id in route_table_ids:
            add_transit_gateway_route(route_table_id, tgw_id, '30.0.0.0/16')
    else:
        print(f"Unable to add route table entry for VPC: {vpc2_id} with routes of {route_table_ids}.")
