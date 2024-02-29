import boto3, os
import logging, json, time
from urllib.request import urlopen

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize the Boto3 client for AWS services
ec2_client = boto3.client('ec2')
s3_client = boto3.client('s3')
bucket_name = os.environ.get('BUCKET_NAME')
object_name = os.environ.get('BUCKET_OBJECT_ID')
tgw_id = os.environ.get('DR_TGW_ID')


def validateEventPayload(event):
    for key in event.keys():
        if key == "body":
            logger.info("Found body parameter block")
            return json.loads(event[key])
    logger.info("Event does not has the body block")
    return event

def get_recovered_vpc_id(event):
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
        tgw_attach_id = response['TransitGatewayVpcAttachment']['TransitGatewayAttachmentId']
        tgw_info = ec2_client.describe_transit_gateway_attachments(TransitGatewayAttachmentIds=[tgw_attach_id])
        state = tgw_info['TransitGatewayAttachments'][0]['State']
        
        if state == 'available':
            break
        
        logging.info(f"Transit Gateway Attachment {tgw_attach_id} is in {state} state. Waiting...")
        time.sleep(5)
    logging.info(f"Transit Gateway Attachment {tgw_attach_id} Created.")
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
        logging.info(f"Error listing route tables for VPC {vpc_id}: {e}")
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
        
        logging.info(f"Added route {destination_cidr_block} to route table {route_table_id} for transit gateway {transit_gateway_id}.")
        return True
    
    except Exception as e:
        logging.info(f"Error adding route to route table {route_table_id}: {e}")
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
    logging.info(f"Unique Az subnets for the Vpc {vpc_id} are {list(subnets_by_az.values())}")
    return list(subnets_by_az.values())

def add_route_to_vpc_route_table(route_table_id, destination_cidr_block, tgw_id):    
    ec2_client.create_route(
        DestinationCidrBlock=destination_cidr_block,                                                                        
        RouteTableId=route_table_id,
        TransitGatewayId=tgw_id
    )

# Example usage
def lambda_handler(event, context):
    logging.info(event)

    response = s3_client.get_object(Bucket=bucket_name, Key=object_name)
    file_content = response['Body'].read().decode('utf-8')

    # Parse the JSON data
    parsed_data = json.loads(file_content)

    # Extract the VPC ID
    vpc1_id = parsed_data.get('VPC-id')

    logging.info(f"Extracted VPC Id from the S3 Bucket {bucket_name}: {vpc1_id}")

    vpc2_id = get_recovered_vpc_id(event)
    logging.info(f"Extracted VPC Id from the payload: {vpc2_id}")

    file = {'VPC-1-id'  : vpc1_id,
            'VPC-2-id'  : vpc2_id}

    response = ec2_client.describe_vpcs(
    VpcIds=[
        vpc2_id,
    ],
    )

    cidr_block_2 = response['Vpcs'][0]['CidrBlock']


    response = ec2_client.describe_vpcs(
    VpcIds=[
        vpc1_id,
    ],
    )

    cidr_block_1 = response['Vpcs'][0]['CidrBlock']

    # Attach VPC1 to Transit Gateway
    subnet_ids_1 = get_unique_subnets_per_az(vpc1_id)
    if subnet_ids_1 is not None:
        attachment_id_vpc1 = attach_vpc_to_transit_gateway(tgw_id, vpc1_id, subnet_ids_1)
    else:
        logging.info(f"Unable to attach Tgw attachment for VPC: {vpc1_id} with subnet {subnet_ids_1}.")
    
    route_table_ids = list_route_tables(vpc1_id)
    
    if route_table_ids is not None:
        # Add transit gateway routes to all route tables
        for route_table_id in route_table_ids:
            add_route_to_vpc_route_table(route_table_id, cidr_block_2, tgw_id)
    else:
        logging.info(f"Unable to add route table entry for VPC: {vpc1_id} with routes of {route_table_ids}.")


    subnet_ids_2 = get_unique_subnets_per_az(vpc2_id)
    if subnet_ids_2 is not None:
        attachment_id_vpc2 = attach_vpc_to_transit_gateway(tgw_id, vpc2_id, subnet_ids_2)
    else:
        logging.info(f"Unable to attach Tgw attachment for VPC: {vpc2_id} with subnet {subnet_ids_2}.")
       
    route_table_ids = list_route_tables(vpc2_id)
    
    if route_table_ids is not None:
        # Add transit gateway routes to all route tables
        for route_table_id in route_table_ids:
            add_route_to_vpc_route_table(route_table_id, cidr_block_1, tgw_id)
    else:
        logging.info(f"Unable to add route table entry for VPC: {vpc2_id} with routes of {route_table_ids}.")

    reset_file = {'VPC-TGW-attachment-1' : attachment_id_vpc1,
                  'VPC-TGW-attachment-2' : attachment_id_vpc2}
    
    s3_client.put_object(Body=json.dumps(file).encode(), Bucket=bucket_name, Key=object_name)
    s3_client.put_object(Body=json.dumps(reset_file).encode(), Bucket=bucket_name, Key='TGW_ATTACH_ID.txt')

    logging.info("Execution Successful...")
    return '200'